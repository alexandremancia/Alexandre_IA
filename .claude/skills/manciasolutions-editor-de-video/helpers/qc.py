"""QC automatizado do render — rode ANTES de mostrar qualquer preview (Regra Dura 18).

O video-use deixa o self-eval por conta do agente, olhando PNG por PNG. Aqui
as checagens que dão para medir viraram código, e sobra para o olho humano só
o que é gosto:

  1. duração do arquivo × duração esperada pelo EDL
  2. resolução, fps, pix_fmt, presença de faixa de áudio
  3. estalo nas junções de corte (descontinuidade amostra a amostra)
  4. loudness integrada × alvo da plataforma
  5. colisão legenda × overlay (Regra Dura 1 falha em silêncio)
  6. frames de cada borda de corte exportados para inspeção visual

Uso:
    python helpers/qc.py edit/final.mp4 --edl edit/edl.json --target tiktok
    python helpers/qc.py edit/final.mp4 --edl edit/edl.json --no-frames
    python helpers/qc.py edit/preview.mp4 --edl edit/edl.json --strict
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

LEVELS = {"ok": "✓", "warn": "⚠", "fail": "✗"}


@dataclass
class Check:
    level: str
    name: str
    detail: str

    def line(self) -> str:
        return f"  {LEVELS[self.level]} {self.name:<26} {self.detail}"


def ffprobe_json(path: Path, args: list[str]) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", *args, "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return {}
    return json.loads(proc.stdout or "{}")


def probe(path: Path) -> dict:
    v = ffprobe_json(path, ["-select_streams", "v:0", "-show_entries",
                            "stream=width,height,r_frame_rate,pix_fmt,codec_name"])
    a = ffprobe_json(path, ["-select_streams", "a:0", "-show_entries",
                            "stream=codec_name,sample_rate,channels"])
    f = ffprobe_json(path, ["-show_entries", "format=duration,bit_rate"])
    out: dict = {}
    if v.get("streams"):
        st = v["streams"][0]
        num, den = st["r_frame_rate"].split("/")
        out.update(width=int(st["width"]), height=int(st["height"]),
                   fps=float(num) / float(den or 1), pix_fmt=st.get("pix_fmt"),
                   vcodec=st.get("codec_name"))
    if a.get("streams"):
        st = a["streams"][0]
        out.update(acodec=st.get("codec_name"), sample_rate=int(st.get("sample_rate", 0)),
                   channels=int(st.get("channels", 0)))
    if f.get("format"):
        out["duration"] = float(f["format"].get("duration", 0))
    return out


def measure_loudness(path: Path) -> dict:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    blob = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    return json.loads(blob.group(0)) if blob else {}


def edl_boundaries(edl: dict) -> tuple[list[float], float]:
    """Instantes das junções na timeline de saída + duração total esperada."""
    bounds: list[float] = []
    t = 0.0
    ranges = edl.get("ranges", [])
    for seg in ranges:
        speed = float(seg.get("speed", 1.0)) or 1.0
        t += (float(seg["end"]) - float(seg["start"])) / speed
        bounds.append(round(t, 3))
    total = t
    return bounds[:-1], total   # a última borda é o fim do arquivo, não uma junção


def read_window(path: Path, center: float, half: float = 0.06, sr: int = 48000):
    """Decodifica uma janela curta de áudio em mono para análise de estalo."""
    import numpy as np

    start = max(0.0, center - half)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "w.wav"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{half * 2:.3f}",
             "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "wav", str(wav)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0 or not wav.exists():
            return None
        with wave.open(str(wav), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
    if not raw:
        return None
    y = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return y


def pop_score(y) -> tuple[float, int]:
    """Assinatura de estalo: (pico do salto em dBFS, largura do pico em amostras).

    O nível do salto sozinho NÃO distingue estalo de conteúdo. Medido em ±60ms
    numa emenda real:

        corte com fade de 30ms   -42.7 dBFS, 2570 amostras no pico
        corte seco (estalo)      -24.3 dBFS,    3 amostras
        batida de bumbo           -4.0 dBFS,   16 amostras
        transiente de fala       -19.2 dBFS,   33 amostras

    O bumbo salta 20 dB MAIS que o estalo — um limiar por nível marcaria toda
    música percussiva e deixaria o estalo passar. O que separa é a LARGURA:
    estalo é um degrau de uma amostra (a forma de onda salta de um valor a
    outro entre dois samples), enquanto qualquer transiente acústico sobe ao
    longo de dezenas de amostras, porque tem envelope de ataque.

    Largura = quantas amostras do sinal de diferença chegam a metade do pico.
    """
    import numpy as np

    if y is None or len(y) < 4:
        return -120.0, 0
    d = np.abs(np.diff(y))
    peak = float(d.max())
    if peak <= 0:
        return -120.0, 0
    width = int((d > peak * 0.5).sum())
    return 20 * math.log10(peak), width


def is_pop(peak_db: float, width: int, floor_db: float = -45.0,
           max_width: int = 8) -> bool:
    """Salto isolado o bastante para ser descontinuidade, e alto o bastante para se ouvir."""
    return peak_db > floor_db and 0 < width <= max_width


def parse_ass_geometry(sub_path: Path) -> tuple[int | None, int | None, int | None]:
    """(MarginV, PlayResX, PlayResY) do .ass.

    A margem só quer dizer alguma coisa em relação ao PlayResY: o captions.py
    grava ali a resolução real da saída, então MarginV=346 num 1080x1920 é 18%
    da altura — correto — enquanto o mesmo 346 num PlayResY=288 seria absurdo.
    Comparar a margem com um número absoluto de pixels não diz nada.
    """
    margin = play_x = play_y = None
    for line in sub_path.read_text(errors="ignore").splitlines():
        if line.startswith("PlayResX:"):
            try:
                play_x = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("PlayResY:"):
            try:
                play_y = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif line.startswith("Style:") and margin is None:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 22:
                try:
                    margin = int(parts[21])
                except ValueError:
                    pass
    return margin, play_x, play_y


# Fração mínima da altura a reservar embaixo, por aspecto. Espelha o
# MARGIN_V_BY_ASPECT do captions.py, com folga: aqui é o piso do que passa,
# não o alvo.
MIN_MARGIN_PCT = {"vertical": 0.13, "quadrado": 0.07, "horizontal": 0.04}


def min_margin_pct(play_x: int, play_y: int) -> tuple[float, str]:
    ratio = play_x / play_y if play_y else 1.0
    if ratio < 0.9:
        return MIN_MARGIN_PCT["vertical"], "vertical"
    if ratio < 1.2:
        return MIN_MARGIN_PCT["quadrado"], "quadrado"
    return MIN_MARGIN_PCT["horizontal"], "horizontal"


def subtitle_times(sub_path: Path) -> list[tuple[float, float]]:
    """Janelas em que existe legenda na tela (.ass ou .srt)."""
    text = sub_path.read_text(errors="ignore")
    out: list[tuple[float, float]] = []
    if sub_path.suffix.lower() == ".ass":
        for line in text.splitlines():
            if line.startswith("Dialogue:"):
                parts = line.split(",", 3)
                out.append((ass_secs(parts[1]), ass_secs(parts[2])))
    else:
        for m in re.finditer(r"(\d\d:\d\d:\d\d,\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d,\d\d\d)", text):
            out.append((srt_secs(m.group(1)), srt_secs(m.group(2))))
    return out


def ass_secs(t: str) -> float:
    h, m, s = t.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def srt_secs(t: str) -> float:
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def overlaps(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def check_caption_collision(edl: dict, edit_dir: Path, duration: float) -> list[Check]:
    """Regra Dura 1: overlay por cima da legenda esconde a legenda, sem erro nenhum."""
    subs = edl.get("subtitles")
    overlays = edl.get("overlays", [])
    if not subs:
        return [Check("ok", "legenda × overlay", "sem legenda no EDL")]
    sub_path = Path(subs)
    if not sub_path.is_absolute():
        sub_path = (edit_dir / sub_path) if (edit_dir / sub_path).exists() else (edit_dir.parent / sub_path)
    if not sub_path.exists():
        return [Check("fail", "legenda × overlay", f"arquivo de legenda não encontrado: {subs}")]
    if not overlays:
        return [Check("ok", "legenda × overlay", "sem overlays")]

    sub_windows = subtitle_times(sub_path)
    margin = play_x = play_y = None
    if sub_path.suffix.lower() == ".ass":
        margin, play_x, play_y = parse_ass_geometry(sub_path)
    checks = []
    risky = 0
    for ov in overlays:
        start = float(ov.get("start_in_output", 0))
        end = start + float(ov.get("duration", 0))
        hit = any(overlaps((start, end), w) for w in sub_windows)
        if not hit:
            continue
        # Overlay com geometria declarada: só é problema se invadir a faixa baixa.
        geom = ov.get("y")
        if geom is None:
            risky += 1
        else:
            checks.append(Check("ok", "legenda × overlay",
                                f"overlay em y={geom} coexiste com legenda"))
    if risky:
        checks.append(Check(
            "warn", "legenda × overlay",
            f"{risky} overlay(s) sem geometria declarada sobrepõem janelas de legenda — "
            f"confirme visualmente que a legenda aparece por cima"))
    if not checks:
        checks.append(Check("ok", "legenda × overlay", f"{len(sub_windows)} janelas, sem conflito"))
    if margin is not None and play_y:
        piso, forma = min_margin_pct(play_x or play_y, play_y)
        pct = margin / play_y
        if pct < piso:
            checks.append(Check(
                "warn", "safe-zone da legenda",
                f"margem de {pct * 100:.0f}% da altura ({margin}px em {play_y}) — "
                f"abaixo do piso de {piso * 100:.0f}% para {forma}"
                + (". A UI de TikTok/Reels/Shorts cobre ~25-30% da base"
                   if forma == "vertical" else "")))
    return checks


def export_frames(path: Path, bounds: list[float], out_dir: Path, window: float = 0.12) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for i, b in enumerate(bounds):
        for label, t in (("antes", max(0.0, b - window)), ("depois", b + window)):
            out = out_dir / f"corte{i:02d}_{b:.2f}s_{label}.png"
            proc = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
                 "-frames:v", "1", str(out)],
                capture_output=True, text=True,
            )
            if proc.returncode == 0:
                n += 1
    return n


TARGETS = {"tiktok": -14.0, "reels": -14.0, "shorts": -14.0, "youtube": -14.0,
           "instagram": -14.0, "podcast": -16.0, "broadcast": -23.0, "cinema": -27.0}

# Teto de pico real da entrega. -1.0 é o limite em que o player começa a clipar;
# o alvo do render é -1.5 para absorver o overshoot do AAC.
TP_CEILING = -1.0


def main() -> None:
    ap = argparse.ArgumentParser(description="QC automatizado do render")
    ap.add_argument("video", type=Path)
    ap.add_argument("--edl", type=Path, default=None)
    ap.add_argument("--edit-dir", type=Path, default=None)
    ap.add_argument("--target", default=None, choices=list(TARGETS), help="Alvo de loudness")
    ap.add_argument("--expect-size", default=None, help="LARGURAxALTURA esperada, ex. 1080x1920")
    ap.add_argument("--pop-floor", type=float, default=-45.0,
                    help="Abaixo deste nível o salto é inaudível e não conta")
    ap.add_argument("--pop-max-width", type=int, default=8,
                    help="Amostras no pico acima das quais o salto é transiente, não estalo")
    ap.add_argument("--duration-tolerance", type=float, default=0.5, help="Diferença tolerada de duração (s)")
    ap.add_argument("--no-frames", action="store_true", help="Não exporta PNGs das bordas")
    ap.add_argument("--strict", action="store_true", help="Sai com código 1 se houver qualquer aviso")
    ap.add_argument("--json", type=Path, default=None, help="Grava o relatório em JSON")
    args = ap.parse_args()

    if not args.video.exists():
        print(f"erro: {args.video} não existe", file=sys.stderr)
        sys.exit(2)

    edit_dir = args.edit_dir or (args.edl.parent if args.edl else args.video.parent)
    checks: list[Check] = []

    info = probe(args.video)
    if not info.get("width"):
        print("erro: arquivo sem faixa de vídeo legível", file=sys.stderr)
        sys.exit(2)

    checks.append(Check("ok", "vídeo", f"{info['width']}x{info['height']} @ {info['fps']:.2f}fps "
                                       f"{info.get('vcodec')} {info.get('pix_fmt')}"))

    if info.get("pix_fmt") and info["pix_fmt"] not in ("yuv420p", "yuvj420p"):
        checks.append(Check("warn", "pix_fmt", f"{info['pix_fmt']} — players web esperam yuv420p"))

    if args.expect_size:
        want = args.expect_size.lower().replace("×", "x")
        got = f"{info['width']}x{info['height']}"
        checks.append(Check("ok" if got == want else "fail", "resolução",
                            f"{got}" + ("" if got == want else f" ≠ esperado {want}")))

    if info.get("acodec"):
        checks.append(Check("ok", "áudio", f"{info['acodec']} {info.get('sample_rate')}Hz "
                                           f"{info.get('channels')}ch"))
    else:
        checks.append(Check("fail", "áudio", "nenhuma faixa de áudio no arquivo"))

    bounds: list[float] = []
    if args.edl:
        edl = json.loads(args.edl.read_text())
        bounds, expected = edl_boundaries(edl)
        actual = info.get("duration", 0)
        diff = actual - expected
        level = "ok" if abs(diff) <= args.duration_tolerance else "fail"
        checks.append(Check(level, "duração",
                            f"{actual:.2f}s (EDL esperava {expected:.2f}s, Δ {diff:+.2f}s)"))
        checks.extend(check_caption_collision(edl, edit_dir, actual))

        # --- estalos nas junções ---
        if bounds and info.get("acodec"):
            piores: list[tuple[float, float, int]] = []
            for b in bounds:
                if b >= actual:
                    continue
                peak, width = pop_score(read_window(args.video, b))
                if is_pop(peak, width, args.pop_floor, args.pop_max_width):
                    piores.append((b, peak, width))
            if piores:
                b, peak, width = max(piores, key=lambda x: x[1])
                checks.append(Check(
                    "warn", "estalo nas junções",
                    f"{len(piores)} de {len(bounds)} junções com salto isolado; "
                    f"pior {peak:.1f} dBFS em {width} amostra(s) aos {b:.2f}s — "
                    f"falta o fade de 30ms (Regra Dura 3)"))
            else:
                checks.append(Check("ok", "estalo nas junções",
                                    f"{len(bounds)} junções, nenhuma descontinuidade isolada"))
    else:
        checks.append(Check("warn", "EDL", "não informado — duração e junções não verificadas"))

    if args.target and info.get("acodec"):
        m = measure_loudness(args.video)
        if m:
            i = float(m.get("input_i", 0))
            tp = float(m.get("input_tp", 0))
            want = TARGETS[args.target]
            delta = i - want
            level = "ok" if abs(delta) <= 1.0 else "warn"
            detalhe = f"{i:.1f} LUFS (alvo {want} para {args.target}, Δ {delta:+.1f})"
            if level == "warn" and delta < 0 and tp >= TP_CEILING - 0.6:
                # Não é desleixo do normalizador: o teto de pico é que prende.
                # Material com razão pico/loudness alta não chega ao alvo só com
                # ganho, e mandar "aumente o volume" faria o editor clipar. O que
                # resolve é compressão de ATAQUE RÁPIDO antes da normalização —
                # medido: cadeia `clean` (8ms) para em -15.2, `loud` (1ms)
                # chega a -14.1. Limiter sozinho não resolve.
                detalhe += (f" — limitado pelo teto de pico (PLR {tp - i:.1f} dB), "
                            f"não por erro de normalização. Para chegar ao alvo: "
                            f"audio_post.py --clean loud --target {args.target}, "
                            f"ao custo de dinâmica")
            checks.append(Check(level, "loudness", detalhe))
            if tp > TP_CEILING:
                checks.append(Check("warn", "pico real",
                                    f"{tp:.1f} dBTP acima do teto de {TP_CEILING} — "
                                    f"risco de clipping no player"))

    frames = 0
    if bounds and not args.no_frames:
        frames = export_frames(args.video, bounds, edit_dir / "verify")
        checks.append(Check("ok", "frames de borda", f"{frames} PNGs em {edit_dir / 'verify'}"))

    print(f"\n── QC: {args.video.name} ──")
    for c in checks:
        print(c.line())

    fails = sum(1 for c in checks if c.level == "fail")
    warns = sum(1 for c in checks if c.level == "warn")
    print(f"\n  {fails} falha(s), {warns} aviso(s)")
    if fails:
        print("  → corrija e re-renderize antes de mostrar ao usuário (máx. 3 ciclos)")
    elif warns:
        print("  → avisos exigem conferência visual nos PNGs de verify/")
    else:
        print("  → aprovado nas checagens automáticas; confira o gosto no olho")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(
            {"video": str(args.video), "checks": [c.__dict__ for c in checks],
             "fails": fails, "warns": warns}, indent=2, ensure_ascii=False))
        print(f"  relatório: {args.json}")

    sys.exit(1 if fails or (args.strict and warns) else 0)


if __name__ == "__main__":
    main()

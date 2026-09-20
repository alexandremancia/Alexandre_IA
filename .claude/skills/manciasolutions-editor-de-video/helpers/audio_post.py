"""Pós de áudio: limpeza de voz, trilha com ducking e loudness por plataforma.

Áudio ruim mata um vídeo mais rápido que imagem ruim. Aqui ficam as três
operações que o CapCut expõe como botões ("reduzir ruído", "volume da
música", "normalizar") e que em ffmpeg são cadeias de filtro.

Regra Dura 14: música entra DEPOIS do loudnorm da fala, com ducking. Somar
música crua na fala já normalizada estoura o pico e desregula a medição.

Uso:
    python helpers/audio_post.py --analyze final.mp4
    python helpers/audio_post.py voz.mp4 -o voz_limpa.mp4 --clean --target tiktok
    python helpers/audio_post.py final.mp4 -o com_trilha.mp4 --music trilha.mp3 --duck --music-db -18
    python helpers/audio_post.py --print-chain --clean          # só imprime o filtro
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Alvos de loudness. Streaming normaliza para perto de -14 LUFS; entregar mais
# alto só faz a plataforma abaixar de volta, com o dinamismo já esmagado.
# (loudness integrada, teto de pico real, faixa dinâmica)
#
# O teto é -1.5 e não -1.0 porque o AAC faz overshoot depois da normalização.
# Medido neste repo, mirando TP=-1: -1.00 dBTP em PCM, -0.62 em AAC 128k e
# +0.30 em AAC 192k — este último clipa no player. Mirar -1.5 entrega -1.05.
TARGETS = {
    "tiktok":    (-14.0, -1.5, 11.0),
    "reels":     (-14.0, -1.5, 11.0),
    "shorts":    (-14.0, -1.5, 11.0),
    "youtube":   (-14.0, -1.5, 11.0),
    "instagram": (-14.0, -1.5, 11.0),
    "podcast":   (-16.0, -1.5, 11.0),
    "spotify":   (-14.0, -1.5, 11.0),
    "broadcast": (-23.0, -2.0, 7.0),   # EBU R128
    "cinema":    (-27.0, -3.0, 15.0),
}

# Cadeias nomeadas. Cada uma é um ponto de partida, não um dogma —
# ouça o material antes de aplicar.
CHAINS = {
    # Voz gravada em ambiente comum: corta rumble, reduz ruído de fundo,
    # controla sibilância, dá corpo e cola a dinâmica.
    "clean": (
        "highpass=f=80,"
        "afftdn=nf=-25:nt=w,"
        "equalizer=f=250:t=q:w=1.2:g=-2,"      # tira o abafado
        "equalizer=f=3200:t=q:w=1.5:g=2,"      # presença/inteligibilidade
        "deesser=i=0.4:m=0.5:f=0.5,"
        "acompressor=threshold=-18dB:ratio=3:attack=8:release=160:makeup=2"
    ),
    # Mais agressivo: gravação ruim, ar-condicionado, sala com eco.
    "rescue": (
        "highpass=f=100,"
        "afftdn=nf=-32:nt=w,"
        "anlmdn=s=0.0002,"
        "equalizer=f=200:t=q:w=1.0:g=-4,"
        "equalizer=f=3500:t=q:w=1.5:g=3,"
        "deesser=i=0.5:m=0.5:f=0.5,"
        "acompressor=threshold=-20dB:ratio=4:attack=5:release=140:makeup=3"
    ),
    # Só o mínimo: fonte já boa (lapela, cabine).
    "gentle": (
        "highpass=f=60,"
        "acompressor=threshold=-16dB:ratio=2:attack=10:release=200:makeup=1"
    ),
    # Para quando o alvo de loudness TEM de ser atingido.
    #
    # Material com razão pico/loudness (PLR) alta não chega a -14 LUFS só com
    # normalização: o teto de pico prende antes. Medido neste repo, numa fala
    # de PLR 17.1 dB, normalizando para I=-14:TP=-1.5 depois de cada cadeia:
    #
    #     sem tratamento                        -20.5 LUFS   PLR 17.1
    #     clean (ataque 8ms, ratio 3)           -15.2 LUFS   PLR 13.7
    #     alimiter sozinho                      -15.5 LUFS   PLR 14.0
    #     esta cadeia (ataque 1ms, ratio 6)     -14.1 LUFS   PLR 12.6  ← no alvo
    #
    # O que resolve é ATAQUE RÁPIDO, não limiter: com 8ms o compressor perde o
    # transiente que define o pico. O custo é dinâmica — não use em material
    # que depende de variação de intensidade.
    "loud": (
        "highpass=f=80,"
        "afftdn=nf=-25:nt=w,"
        "equalizer=f=250:t=q:w=1.2:g=-2,"
        "equalizer=f=3200:t=q:w=1.5:g=2,"
        "deesser=i=0.4:m=0.5:f=0.5,"
        "acompressor=threshold=-24dB:ratio=6:attack=1:release=80:makeup=2"
    ),

    # Telefone/rádio, para efeito criativo.
    "phone": "highpass=f=400,lowpass=f=3400,acompressor=threshold=-14dB:ratio=6",
    "none": "",
}


def run(cmd: list[str], quiet: bool = False) -> subprocess.CompletedProcess:
    if not quiet:
        print("  $", " ".join(str(c) for c in cmd[:14]), "..." if len(cmd) > 14 else "")
    return subprocess.run(cmd, capture_output=True, text=True)


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("erro: ffmpeg/ffprobe não estão no PATH", file=sys.stderr)
        sys.exit(1)


def measure(path: Path) -> dict:
    """ebur128 via loudnorm print_format=json — mede sem alterar nada."""
    proc = run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", "loudnorm=print_format=json", "-f", "null", "-"],
        quiet=True,
    )
    blob = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", proc.stderr, re.S)
    if not blob:
        return {}
    return json.loads(blob.group(0))


def has_audio(path: Path) -> bool:
    proc = run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(path)],
        quiet=True,
    )
    return bool(proc.stdout.strip())


def loudnorm_filter(target: str, measured: dict | None = None) -> str:
    i, tp, lra = TARGETS[target]
    base = f"loudnorm=I={i}:TP={tp}:LRA={lra}"
    if measured and all(k in measured for k in ("input_i", "input_tp", "input_lra", "input_thresh")):
        # Segundo passe: com as medidas do primeiro, a normalização vira linear
        # (sem bombeamento dinâmico). É por isso que se mede antes.
        base += (
            f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            ":linear=true:print_format=summary"
        )
    return base


def build_voice_chain(clean: str | None, target: str | None, measured: dict | None) -> str:
    parts = []
    if clean and CHAINS.get(clean):
        parts.append(CHAINS[clean])
    if target:
        parts.append(loudnorm_filter(target, measured))
    parts.append("aresample=48000")
    return ",".join(p for p in parts if p)


def build_music_graph(
    music_db: float,
    duck: bool,
    duck_ratio: float,
    fade_in: float,
    fade_out: float,
    music_duration: float,
) -> str:
    """Grafo: [0:a] voz, [1:a] música → [aout].

    Com ducking, a voz vira a cadeia lateral de um compressor na música: cada
    vez que alguém fala, a trilha abaixa sozinha e volta no silêncio.
    """
    music_pre = (
        f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"volume={music_db}dB,"
        f"afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={max(0.0, music_duration - fade_out):.3f}:d={fade_out}[music];"
    )
    voice_pre = "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[voice];"

    if duck:
        return (
            voice_pre + music_pre +
            "[voice]asplit=2[voice_out][voice_sc];"
            f"[music][voice_sc]sidechaincompress="
            f"threshold=0.03:ratio={duck_ratio}:attack=15:release=350:makeup=1[music_ducked];"
            "[voice_out][music_ducked]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        )
    return (
        voice_pre + music_pre +
        "[voice][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
    )


def probe_duration(path: Path) -> float:
    proc = run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        quiet=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def report(path: Path) -> None:
    m = measure(path)
    if not m:
        print(f"{path}: não foi possível medir (tem faixa de áudio?)")
        return
    i = float(m.get("input_i", 0))
    tp = float(m.get("input_tp", 0))
    lra = float(m.get("input_lra", 0))
    print(f"\n── loudness: {path.name} ──")
    print(f"  integrada   {i:>7.1f} LUFS")
    print(f"  pico real   {tp:>7.1f} dBTP")
    print(f"  faixa (LRA) {lra:>7.1f} LU")
    for name, (ti, ttp, _) in TARGETS.items():
        if name in ("reels", "shorts", "instagram", "spotify"):
            continue
        delta = ti - i
        flag = "ok" if abs(delta) < 1.0 else f"{delta:+.1f} LU"
        print(f"  {name:<10} alvo {ti:>6.1f}  →  {flag}")
    if tp > -1.0:
        print("  ⚠ pico real acima de -1 dBTP: risco de clipping ao codificar para AAC")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pós de áudio: limpeza, trilha com ducking, loudness")
    ap.add_argument("input", type=Path, nargs="?", help="Vídeo ou áudio de entrada")
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--analyze", action="store_true", help="Só mede loudness e sai")
    ap.add_argument("--clean", nargs="?", const="clean", default=None,
                    choices=list(CHAINS), help="Cadeia de limpeza de voz")
    ap.add_argument("--target", default=None, choices=list(TARGETS), help="Alvo de loudness")
    ap.add_argument("--music", type=Path, default=None, help="Trilha a mixar")
    ap.add_argument("--music-db", type=float, default=-20.0, help="Ganho da trilha em dB (padrão -20)")
    ap.add_argument("--duck", action="store_true", help="Abaixa a trilha automaticamente sob a fala")
    ap.add_argument("--duck-ratio", type=float, default=8.0, help="Intensidade do ducking (padrão 8)")
    ap.add_argument("--fade-in", type=float, default=1.0)
    ap.add_argument("--fade-out", type=float, default=2.0)
    ap.add_argument("--list-chains", action="store_true")
    ap.add_argument("--print-chain", action="store_true", help="Imprime o filtro e sai, sem renderizar")
    args = ap.parse_args()

    if args.list_chains:
        for name, chain in CHAINS.items():
            print(f"\n{name}:\n  {chain or '(sem filtro)'}")
        return

    if args.print_chain:
        print(build_voice_chain(args.clean, args.target, None))
        return

    require_ffmpeg()

    if not args.input:
        ap.error("informe o arquivo de entrada")
    if not args.input.exists():
        print(f"erro: {args.input} não existe", file=sys.stderr)
        sys.exit(1)

    if args.analyze:
        report(args.input)
        return

    if not args.output:
        ap.error("-o/--output é obrigatório fora do modo --analyze")
    if not has_audio(args.input):
        print(f"erro: {args.input} não tem faixa de áudio", file=sys.stderr)
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    # Passe 1: mede, para o loudnorm do passe 2 virar linear.
    measured = None
    if args.target:
        print("→ medindo loudness (passe 1/2)")
        probe_src = args.input
        measured = measure(probe_src)

    voice_chain = build_voice_chain(args.clean, args.target, measured)

    if args.music:
        if not args.music.exists():
            print(f"erro: {args.music} não existe", file=sys.stderr)
            sys.exit(1)
        # Regra Dura 14: a voz é tratada e normalizada ANTES de a música entrar.
        # Isso exige dois passes, então o intermediário fica ao lado da saída.
        tmp = args.output.with_name(args.output.stem + ".voz_tmp.mp4")
        print("→ tratando a voz")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(args.input)]
        cmd += ["-af", voice_chain] if voice_chain else []
        cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(tmp)]
        proc = run(cmd)
        if proc.returncode != 0:
            print(proc.stderr[-2000:], file=sys.stderr)
            sys.exit(1)

        dur = probe_duration(tmp)
        graph = build_music_graph(args.music_db, args.duck, args.duck_ratio,
                                  args.fade_in, args.fade_out, dur)
        print(f"→ mixando trilha ({'com' if args.duck else 'sem'} ducking)")
        proc = run([
            "ffmpeg", "-y", "-v", "error",
            "-i", str(tmp), "-stream_loop", "-1", "-i", str(args.music),
            "-filter_complex", graph,
            "-map", "0:v?", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(args.output),
        ])
        if proc.returncode != 0:
            print(proc.stderr[-2000:], file=sys.stderr)
            sys.exit(1)
        tmp.unlink(missing_ok=True)
    else:
        print("→ processando áudio")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(args.input)]
        cmd += ["-af", voice_chain] if voice_chain else []
        cmd += ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(args.output)]
        proc = run(cmd)
        if proc.returncode != 0:
            print(proc.stderr[-2000:], file=sys.stderr)
            sys.exit(1)

    print(f"✓ {args.output}")
    report(args.output)


if __name__ == "__main__":
    main()

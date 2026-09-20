"""Detecta BPM, grade de batidas e picos de energia de uma trilha.

Serve para montagem sincronizada com música (o "beat sync" do CapCut):
cortes caem na batida, overlays entram no downbeat, e as viradas da faixa
viram pontos de estrutura.

Usa librosa quando disponível (melhor); cai para um detector próprio em
numpy + ffmpeg quando não (fluxo espectral + autocorrelação). O formato de
saída é o mesmo nos dois caminhos — mas o relatório sempre diz qual rodou.

Uso:
    python helpers/beats.py musica.mp3 -o edit/beats.json
    python helpers/beats.py musica.mp3 --snap edit/edl.json -o edit/edl_snapped.json
    python helpers/beats.py musica.mp3 --every 4      # só os downbeats (1 a cada 4)
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

SR = 22050


def decode_mono(path: Path, sr: int = SR):
    """Decodifica com ffmpeg para PCM mono e devolve (samples float, sr)."""
    import numpy as np

    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg não está no PATH")
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(path),
             "-ac", "1", "-ar", str(sr), "-f", "wav", str(wav)],
            check=True,
        )
        with wave.open(str(wav), "rb") as wf:
            n = wf.getnframes()
            raw = wf.readframes(n)
            width = wf.getsampwidth()
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
    y = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    y /= float(np.iinfo(dtype).max)
    return y, sr


def onset_envelope(y, sr: int, hop: int = 512):
    """Fluxo espectral positivo — energia que SOBE de um frame para o outro."""
    import numpy as np

    win = 2048
    if len(y) < win:
        return np.zeros(1, dtype=np.float32), hop
    n_frames = 1 + (len(y) - win) // hop
    window = np.hanning(win).astype(np.float32)
    prev = None
    env = np.zeros(n_frames, dtype=np.float32)
    for i in range(n_frames):
        frame = y[i * hop: i * hop + win] * window
        mag = np.abs(np.fft.rfft(frame))
        if prev is not None:
            diff = mag - prev
            env[i] = float(np.sum(diff[diff > 0]))
        prev = mag
    if env.max() > 0:
        env /= env.max()
    return env, hop


def estimate_tempo(env, sr: int, hop: int, bpm_min: float = 60.0, bpm_max: float = 200.0) -> float:
    """Autocorrelação do envelope, restrita a uma faixa musical plausível."""
    import numpy as np

    if len(env) < 4:
        return 0.0
    e = env - env.mean()
    ac = np.correlate(e, e, mode="full")[len(e) - 1:]
    fps = sr / hop
    lag_min = max(1, int(fps * 60.0 / bpm_max))
    lag_max = min(len(ac) - 1, int(fps * 60.0 / bpm_min))
    if lag_max <= lag_min:
        return 0.0
    best = int(np.argmax(ac[lag_min:lag_max])) + lag_min
    return float(60.0 * fps / best)


def beats_from_tempo(env, sr: int, hop: int, bpm: float):
    """Fase da grade: desliza um pente de batidas e fica com o melhor encaixe."""
    import numpy as np

    if bpm <= 0:
        return []
    fps = sr / hop
    period = 60.0 / bpm * fps
    duration_frames = len(env)
    best_phase, best_score = 0.0, -1.0
    for phase in np.arange(0, period, max(1.0, period / 32)):
        idx = np.arange(phase, duration_frames, period).astype(int)
        idx = idx[idx < duration_frames]
        score = float(env[idx].sum())
        if score > best_score:
            best_score, best_phase = score, float(phase)
    idx = np.arange(best_phase, duration_frames, period).astype(int)
    idx = idx[idx < duration_frames]
    return [round(float(i) * hop / sr, 3) for i in idx]


def analyze_librosa(path: Path):
    import librosa
    import numpy as np

    y, sr = librosa.load(str(path), sr=SR, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    rms = librosa.feature.rms(y=y)[0]
    rms_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr)
    tempo_val = float(tempo if np.isscalar(tempo) else tempo[0])
    return {
        "engine": "librosa",
        "bpm": round(tempo_val, 2),
        "duration_s": round(float(len(y) / sr), 3),
        "beats": [round(float(t), 3) for t in beat_times],
        "energy": [[round(float(t), 3), round(float(v), 5)] for t, v in zip(rms_times[::8], rms[::8])],
    }


def analyze_fallback(path: Path):
    import numpy as np

    y, sr = decode_mono(path)
    env, hop = onset_envelope(y, sr)
    bpm = estimate_tempo(env, sr, hop)
    beats = beats_from_tempo(env, sr, hop, bpm)
    step = max(1, len(env) // 400)
    energy = [[round(i * hop / sr, 3), round(float(env[i]), 5)] for i in range(0, len(env), step)]
    return {
        "engine": "numpy-fallback",
        "bpm": round(bpm, 2),
        "duration_s": round(len(y) / sr, 3),
        "beats": beats,
        "energy": energy,
    }


def find_sections(energy: list[list[float]], n: int = 6, min_rel_jump: float = 0.15) -> list[float]:
    """Pontos de virada: maiores saltos de energia média entre janelas vizinhas.

    `min_rel_jump` é o piso: um salto precisa valer pelo menos essa fração da
    amplitude total da faixa para contar. Sem esse piso, uma trilha de energia
    constante devolve as N maiores flutuações de ruído como se fossem estrutura —
    e uma virada inventada faz o editor cortar onde não há nada acontecendo.
    """
    if len(energy) < 8:
        return []
    vals = [e[1] for e in energy]
    times = [e[0] for e in energy]
    amplitude = max(vals) - min(vals)
    if amplitude <= 1e-9:
        return []
    floor = amplitude * min_rel_jump

    w = max(2, len(vals) // 40)
    deltas = []
    for i in range(w, len(vals) - w):
        before = sum(vals[i - w:i]) / w
        after = sum(vals[i:i + w]) / w
        jump = abs(after - before)
        if jump >= floor:
            deltas.append((jump, times[i]))
    deltas.sort(reverse=True)

    picked: list[float] = []
    for _, t in deltas:
        if all(abs(t - p) > 4.0 for p in picked):
            picked.append(t)
        if len(picked) >= n:
            break
    return sorted(picked)


def snap_edl(edl: dict, beats: list[float], tolerance: float = 0.25) -> tuple[dict, int]:
    """Puxa as bordas dos segmentos para a batida mais próxima, dentro da tolerância.

    Nunca move além da tolerância: cortar fora da palavra para acertar a batida
    quebra a Regra Dura 6. Quem decide o trade-off é o editor, não o snap.
    """
    moved = 0
    offset = 0.0
    for seg in edl.get("ranges", []):
        dur = float(seg["end"]) - float(seg["start"])
        for edge, t_out in (("start", offset), ("end", offset + dur)):
            if not beats:
                continue
            nearest = min(beats, key=lambda b: abs(b - t_out))
            delta = nearest - t_out
            if 0 < abs(delta) <= tolerance:
                seg[edge] = round(float(seg[edge]) + delta, 3)
                moved += 1
        offset += float(seg["end"]) - float(seg["start"])
    return edl, moved


def main() -> None:
    ap = argparse.ArgumentParser(description="Detecta BPM, batidas e energia de uma faixa")
    ap.add_argument("audio", type=Path, help="Arquivo de áudio ou vídeo com trilha")
    ap.add_argument("-o", "--output", type=Path, default=None, help="JSON de saída")
    ap.add_argument("--every", type=int, default=1, help="Mantém 1 batida a cada N (4 = downbeats em 4/4)")
    ap.add_argument("--snap", type=Path, default=None, help="edl.json cujas bordas devem ir para a batida")
    ap.add_argument("--tolerance", type=float, default=0.25, help="Deslocamento máximo do snap (s)")
    ap.add_argument("--force-fallback", action="store_true", help="Ignora librosa (para testar o caminho sem deps)")
    args = ap.parse_args()

    if not args.audio.exists():
        print(f"erro: {args.audio} não existe", file=sys.stderr)
        sys.exit(1)

    if args.force_fallback:
        result = analyze_fallback(args.audio)
    else:
        try:
            result = analyze_librosa(args.audio)
        except ImportError:
            print("librosa indisponível — usando detector em numpy (menos preciso)", file=sys.stderr)
            result = analyze_fallback(args.audio)

        # Zero batidas não é resposta, é ausência de resposta. Acontece em
        # material sem transiente (pad, drone, seno modulado): o onset do
        # librosa não vê ataque nenhum, enquanto o fluxo espectral cru ainda
        # pega a modulação de amplitude. Devolver a grade vazia em silêncio
        # faria o --snap não mover nada sem nunca dizer por quê.
        if not result["beats"] or result["bpm"] <= 0:
            print("librosa não encontrou batida alguma (material sem transiente?) — "
                  "tentando o detector em numpy", file=sys.stderr)
            alt = analyze_fallback(args.audio)
            if alt["beats"]:
                alt["engine"] += " (librosa não achou nada)"
                result = alt

    if not result["beats"]:
        print("⚠ nenhuma batida detectada por nenhum dos dois motores.", file=sys.stderr)
        print("  Confira se a faixa tem pulso audível. Sem grade de batidas, "
              "--snap não move borda nenhuma.", file=sys.stderr)

    if args.every > 1:
        result["beats"] = result["beats"][::args.every]
        result["beat_grid"] = f"1 a cada {args.every}"

    result["sections"] = find_sections(result["energy"])

    print(f"engine     {result['engine']}")
    print(f"bpm        {result['bpm']}")
    print(f"duração    {result['duration_s']}s")
    print(f"batidas    {len(result['beats'])}")
    print(f"viradas    {', '.join(f'{t:.1f}s' for t in result['sections']) or '—'}")

    if args.snap:
        edl = json.loads(args.snap.read_text())
        edl, moved = snap_edl(edl, result["beats"], args.tolerance)
        out = args.output or args.snap.with_name(args.snap.stem + "_snapped.json")
        out.write_text(json.dumps(edl, indent=2, ensure_ascii=False))
        print(f"✓ {out}  ({moved} bordas movidas para a batida)")
        return

    out = args.output or args.audio.with_suffix(".beats.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2))
    print(f"✓ {out}")


if __name__ == "__main__":
    main()

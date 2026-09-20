"""Auto-reframe: 16:9 → 9:16 / 1:1 / 4:5 seguindo o sujeito.

É o "enquadramento automático" do CapCut. Detecta onde está o sujeito quadro
a quadro, suaviza a trajetória e recorta acompanhando — em vez do corte
central burro que decapita quem está fora do centro.

Regra Dura 15: trajetória SEM suavização treme. A câmera virtual aqui tem
três freios: média móvel, zona morta (não reage a micro-movimento) e limite
de velocidade (não dá salto). Sem os três, o resultado balança.

Detecção em camadas: rosto (Haar no OpenCV 4, YuNet no OpenCV 5) → energia de
movimento (numpy) → centro fixo. Sempre reporta qual camada respondeu.

Uso:
    python helpers/reframe.py entrada.mp4 -o vertical.mp4 --aspect 9:16
    python helpers/reframe.py entrada.mp4 -o quadrado.mp4 --aspect 1:1 --static
    python helpers/reframe.py entrada.mp4 --analyze-only -o edit/verify/track.json
    python helpers/reframe.py entrada.mp4 --print-filter --aspect 9:16
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

ASPECTS = {
    "9:16": (9, 16),
    "1:1": (1, 1),
    "4:5": (4, 5),
    "16:9": (16, 9),
    "4:3": (4, 3),
    "2.39:1": (239, 100),
}

OUT_SIZES = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
    "16:9": (1920, 1080),
    "4:3": (1440, 1080),
    "2.39:1": (1920, 804),
}


def probe(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,nb_frames",
         "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(proc.stdout)
    st = data["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    fps = float(num) / float(den or 1)
    return {
        "width": int(st["width"]),
        "height": int(st["height"]),
        "fps": fps,
        "duration": float(data["format"]["duration"]),
    }


# ---------------------------------------------------------------------------
# Detecção
# ---------------------------------------------------------------------------


# Modelo YuNet: onde procurar e de onde baixar. Nunca baixado automaticamente —
# buscar arquivo na rede é uma ação que o usuário não pediu.
# Tem de ser media.githubusercontent.com: o modelo está em Git LFS, e a URL
# /raw/ devolve o ponteiro de texto do LFS, não o .onnx. O ponteiro baixa sem
# erro e só falha depois, no parse do ONNX — vale checar o tamanho (~232 KB).
YUNET_URL = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/"
             "models/face_detection_yunet/face_detection_yunet_2023mar.onnx")
YUNET_CACHE = Path.home() / ".cache" / "manciasolutions" / "face_detection_yunet.onnx"


def make_face_detector(model_path: Path | None = None):
    """Devolve (detectar, nome_do_motor) ou (None, motivo).

    Duas APIs de OpenCV convivem no mundo real e é preciso suportar as duas:

      - OpenCV 4.x: Haar cascade (`cv2.CascadeClassifier` + `cv2.data.haarcascades`).
        Rápido, ruim com rosto de perfil e com pouca luz, mas vem dentro do wheel.
      - OpenCV 5.x: os cascades foram REMOVIDOS. Sobrou `cv2.FaceDetectorYN`
        (YuNet, uma DNN) — bem melhor, mas exige um arquivo .onnx separado.

    Sem nenhum dos dois, devolve None e quem chama cai para energia de movimento.
    """
    try:
        import cv2
    except ImportError:
        return None, "opencv não instalado"

    # --- OpenCV 4.x: Haar ---
    if hasattr(cv2, "CascadeClassifier") and hasattr(cv2, "data"):
        frontal = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        profile = Path(cv2.data.haarcascades) / "haarcascade_profileface.xml"
        if frontal.exists():
            front = cv2.CascadeClassifier(str(frontal))
            prof = cv2.CascadeClassifier(str(profile)) if profile.exists() else None
            if not front.empty():
                def detect_haar(frame_bgr):
                    gray = cv2.equalizeHist(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY))
                    faces = front.detectMultiScale(gray, 1.15, 5, minSize=(24, 24))
                    if len(faces) == 0 and prof is not None:
                        faces = prof.detectMultiScale(gray, 1.15, 5, minSize=(24, 24))
                    if len(faces) == 0:
                        return None
                    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                    return float(x + w / 2), float(y + h / 2)
                return detect_haar, "haar"

    # --- OpenCV 5.x: YuNet ---
    if hasattr(cv2, "FaceDetectorYN"):
        model = model_path or YUNET_CACHE
        if not model.exists():
            return None, (
                f"OpenCV {getattr(cv2, '__version__', '5.x')} não traz Haar cascade e o "
                f"modelo YuNet não está em {model}.\n"
                f"    Para habilitar rastreio de rosto:\n"
                f"      mkdir -p {model.parent} && curl -L -o {model} {YUNET_URL}\n"
                f"    Sem ele, o reframe segue por energia de movimento."
            )
        detector = cv2.FaceDetectorYN.create(str(model), "", (320, 320), 0.6, 0.3, 5000)

        def detect_yunet(frame_bgr):
            h, w = frame_bgr.shape[:2]
            detector.setInputSize((w, h))
            _, faces = detector.detect(frame_bgr)
            if faces is None or len(faces) == 0:
                return None
            box = max(faces, key=lambda f: f[2] * f[3])
            return float(box[0] + box[2] / 2), float(box[1] + box[3] / 2)
        return detect_yunet, "yunet"

    return None, "opencv sem API de detecção de rosto"


def track_faces(path: Path, sample_fps: float, info: dict, model_path: Path | None = None):
    """Centro do maior rosto por amostra. Devolve (times, xs, ys, hits, motor)."""
    import cv2
    import numpy as np

    detect, engine = make_face_detector(model_path)
    if detect is None:
        raise RuntimeError(engine)

    cap = cv2.VideoCapture(str(path))
    step = max(1, int(round(info["fps"] / sample_fps)))
    times, xs, ys = [], [], []
    hits = 0
    idx = 0
    prev_gray = None
    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            t = idx / info["fps"]
            # Detecta em meia resolução: 4x mais rápido, precisão suficiente
            # para uma câmera virtual que já é suavizada depois.
            small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
            found = detect(small)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if found is not None:
                cx, cy = found[0] * 2, found[1] * 2
                hits += 1
            elif prev_gray is not None:
                cx, cy = motion_centroid(prev_gray, gray, np)
                cx, cy = cx * 2, cy * 2
            else:
                cx, cy = info["width"] / 2, info["height"] / 2
            times.append(t)
            xs.append(float(cx))
            ys.append(float(cy))
            prev_gray = gray
        idx += 1
    cap.release()
    return times, xs, ys, hits, engine


def motion_centroid(prev_gray, gray, np):
    """Centro de massa da diferença entre dois frames — onde algo se moveu."""
    diff = np.abs(gray.astype(np.int16) - prev_gray.astype(np.int16)).astype(np.float32)
    if diff.sum() < 1e-3:
        h, w = gray.shape
        return w / 2, h / 2
    col = diff.sum(axis=0)
    row = diff.sum(axis=1)
    xs = np.arange(len(col))
    ys = np.arange(len(row))
    return float((col * xs).sum() / col.sum()), float((row * ys).sum() / row.sum())


def track_motion_only(path: Path, sample_fps: float, info: dict):
    """Camada 2: sem OpenCV instalado ou sem rosto nenhum — segue movimento."""
    import numpy as np

    w, h = info["width"], info["height"]
    sw, sh = 160, max(2, int(160 * h / w))
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-vf", f"fps={sample_fps},scale={sw}:{sh},format=gray",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        stdout=subprocess.PIPE,
    )
    frame_size = sw * sh
    times, xs, ys = [], [], []
    prev = None
    i = 0
    while True:
        buf = proc.stdout.read(frame_size)
        if len(buf) < frame_size:
            break
        frame = np.frombuffer(buf, dtype=np.uint8).reshape(sh, sw)
        if prev is not None:
            cx, cy = motion_centroid(prev, frame, np)
            times.append(i / sample_fps)
            xs.append(cx * w / sw)
            ys.append(cy * h / sh)
        prev = frame
        i += 1
    proc.stdout.close()
    proc.wait()
    if not times:
        return [0.0], [w / 2], [h / 2], 0
    return times, xs, ys, 0


# ---------------------------------------------------------------------------
# Suavização (Regra Dura 15)
# ---------------------------------------------------------------------------


def smooth_track(
    values: list[float],
    times: list[float],
    window_s: float,
    deadzone: float,
    max_speed: float,
) -> list[float]:
    """Média móvel → zona morta → limite de velocidade. Nessa ordem."""
    if not values:
        return values
    n = len(values)
    dt = (times[-1] - times[0]) / max(1, n - 1) if n > 1 else 1.0
    win = max(1, int(round(window_s / dt)) | 1)  # ímpar, para centralizar
    half = win // 2

    # 1. média móvel
    avg = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        avg.append(sum(values[lo:hi]) / (hi - lo))

    # 2 + 3. zona morta e velocidade máxima, em uma passada
    out = [avg[0]]
    for i in range(1, n):
        cur = out[-1]
        target = avg[i]
        delta = target - cur
        if abs(delta) < deadzone:
            out.append(cur)          # micro-movimento: câmera não reage
            continue
        # a zona morta não é degrau: só o excedente conta
        delta -= math.copysign(deadzone, delta)
        max_step = max_speed * dt
        if abs(delta) > max_step:
            delta = math.copysign(max_step, delta)
        out.append(cur + delta)
    return out


def clamp_crop(centers: list[float], crop_size: int, frame_size: int) -> list[int]:
    """Converte centro → canto superior/esquerdo, preso dentro do quadro."""
    limit = max(0, frame_size - crop_size)
    return [int(round(min(max(c - crop_size / 2, 0), limit))) for c in centers]


def jitter_score(positions: list[int], dt: float) -> float:
    """Velocidade média da câmera, em px/s."""
    if len(positions) < 2:
        return 0.0
    total = sum(abs(positions[i] - positions[i - 1]) for i in range(1, len(positions)))
    return total / (len(positions) - 1) / max(dt, 1e-6)


def reversal_rate(positions: list[int], dt: float, min_step: float = 2.0) -> float:
    """Inversões de direção por segundo — a medida que de fato detecta tremor.

    Velocidade sozinha não distingue as duas coisas: um sujeito atravessando o
    quadro exige uma panorâmica rápida, e marcá-la como tremor faria o aviso
    gritar em todo movimento legítimo. O que treme é a câmera que vai e volta.
    Panorâmica suave = velocidade alta, poucas inversões. Tremor = inversões
    frequentes, mesmo devagar.

    Passos abaixo de `min_step` px são ruído de arredondamento e não contam
    como direção.
    """
    if len(positions) < 3:
        return 0.0
    deltas = [positions[i] - positions[i - 1] for i in range(1, len(positions))]
    signs = [(1 if d > min_step else (-1 if d < -min_step else 0)) for d in deltas]
    reversals = 0
    last = 0
    for sgn in signs:
        if sgn == 0:
            continue
        if last != 0 and sgn != last:
            reversals += 1
        last = sgn
    span = (len(positions) - 1) * max(dt, 1e-6)
    return reversals / span


# ---------------------------------------------------------------------------
# Saída
# ---------------------------------------------------------------------------


def build_sendcmd(times: list[float], xs: list[int], ys: list[int], out: Path) -> Path:
    lines = []
    last = (None, None)
    for t, x, y in zip(times, xs, ys):
        if (x, y) == last:
            continue
        lines.append(f"{t:.3f} crop x {x};")
        lines.append(f"{t:.3f} crop y {y};")
        last = (x, y)
    out.write_text("\n".join(lines) + "\n")
    return out


def build_filter(cw: int, ch: int, x0: int, y0: int, ow: int, oh: int, cmds: Path | None) -> str:
    head = f"sendcmd=f='{cmds}'," if cmds else ""
    return f"{head}crop=w={cw}:h={ch}:x={x0}:y={y0},scale={ow}:{oh}:flags=lanczos,setsar=1"


def main() -> None:
    ap = argparse.ArgumentParser(description="Auto-reframe com rastreio de sujeito")
    ap.add_argument("input", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--aspect", default="9:16", choices=list(ASPECTS))
    ap.add_argument("--static", action="store_true", help="Um enquadramento fixo (posição média), sem panorâmica")
    ap.add_argument("--sample-fps", type=float, default=4.0, help="Amostras de rastreio por segundo")
    ap.add_argument("--smooth-window", type=float, default=1.5, help="Janela da média móvel (s)")
    ap.add_argument("--deadzone", type=float, default=24.0, help="Movimento ignorado (px do frame original)")
    ap.add_argument("--max-speed", type=float, default=120.0, help="Velocidade máxima da câmera (px/s)")
    ap.add_argument("--zoom", type=float, default=1.0, help=">1 aproxima antes de recortar (ex. 1.1)")
    ap.add_argument("--analyze-only", action="store_true", help="Só rastreia e grava o JSON")
    ap.add_argument("--print-filter", action="store_true", help="Imprime o filtro ffmpeg e sai")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--no-faces", action="store_true", help="Pula a detecção de rosto (só movimento)")
    ap.add_argument("--face-model", type=Path, default=None,
                    help=f"Modelo YuNet .onnx (padrão: {YUNET_CACHE}). Só usado no OpenCV 5.x")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        print("erro: ffmpeg não está no PATH", file=sys.stderr)
        sys.exit(1)
    if not args.input.exists():
        print(f"erro: {args.input} não existe", file=sys.stderr)
        sys.exit(1)

    info = probe(args.input)
    W, H = info["width"], info["height"]
    aw, ah = ASPECTS[args.aspect]
    ow, oh = OUT_SIZES[args.aspect]

    # Maior retângulo do aspecto alvo que cabe no quadro original.
    cw = min(W, int(H * aw / ah))
    ch = min(H, int(W * ah / aw))
    cw = int(cw / args.zoom) & ~1
    ch = int(ch / args.zoom) & ~1
    cw, ch = min(cw, W), min(ch, H)

    print(f"entrada   {W}x{H} @ {info['fps']:.2f}fps  {info['duration']:.1f}s")
    print(f"recorte   {cw}x{ch}  →  saída {ow}x{oh} ({args.aspect})")

    # --- rastreio ---
    engine = "centro-fixo"
    hits = 0
    if args.no_faces:
        times, xs, ys, hits = track_motion_only(args.input, args.sample_fps, info)
        engine = "movimento"
    else:
        try:
            times, xs, ys, hits, backend = track_faces(
                args.input, args.sample_fps, info, args.face_model)
            engine = f"rosto/{backend} ({hits}/{len(times)} amostras) + movimento"
        except Exception as exc:
            # Regra Dura 19: degradar é permitido, degradar calado não é.
            print(f"  ⚠ rastreio de rosto indisponível: {exc}", file=sys.stderr)
            print("  → seguindo por energia de movimento", file=sys.stderr)
            times, xs, ys, hits = track_motion_only(args.input, args.sample_fps, info)
            engine = "movimento"

    if not times:
        times, xs, ys = [0.0], [W / 2], [H / 2]

    print(f"rastreio  {engine}, {len(times)} amostras")

    dt = (times[-1] - times[0]) / max(1, len(times) - 1) if len(times) > 1 else 1.0

    if args.static:
        mx = sum(xs) / len(xs)
        my = sum(ys) / len(ys)
        sx = clamp_crop([mx], cw, W)
        sy = clamp_crop([my], ch, H)
        cmds = None
        x0, y0 = sx[0], sy[0]
        jx = jy = 0.0
        track_out = {"mode": "static", "x": x0, "y": y0}
    else:
        sxs = smooth_track(xs, times, args.smooth_window, args.deadzone, args.max_speed)
        sys_ = smooth_track(ys, times, args.smooth_window, args.deadzone, args.max_speed)
        cx = clamp_crop(sxs, cw, W)
        cy = clamp_crop(sys_, ch, H)
        jx, jy = jitter_score(cx, dt), jitter_score(cy, dt)
        rx, ry = reversal_rate(cx, dt), reversal_rate(cy, dt)
        x0, y0 = cx[0], cy[0]
        track_out = {
            "mode": "tracked",
            "samples": [[round(t, 3), x, y] for t, x, y in zip(times, cx, cy)],
            "speed_x_px_s": round(jx, 2),
            "speed_y_px_s": round(jy, 2),
            "reversals_x_per_s": round(rx, 2),
            "reversals_y_per_s": round(ry, 2),
        }

    meta = {
        "input": str(args.input),
        "source": {"w": W, "h": H, "fps": info["fps"], "duration": info["duration"]},
        "crop": {"w": cw, "h": ch},
        "output": {"w": ow, "h": oh, "aspect": args.aspect},
        "engine": engine,
        "face_hits": hits,
        **track_out,
    }

    if not args.static:
        print(f"câmera    {jx:.0f} px/s (x), {jy:.0f} px/s (y)")
        print(f"tremor    {max(rx, ry):.2f} inversões/s", end="")
        if max(rx, ry) > 1.0:
            print("  ⚠ a câmera vai e volta — aumente --smooth-window ou --deadzone")
        elif max(jx, jy) > 200:
            print("  ⚠ panorâmica muito rápida — considere --static ou --max-speed menor")
        else:
            print("  ok")

    if args.analyze_only:
        out = args.output or args.input.with_suffix(".reframe.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(meta, indent=2))
        print(f"✓ {out}")
        return

    out_video = args.output
    if not out_video and not args.print_filter:
        ap.error("-o/--output é obrigatório")

    cmds_path = None
    if not args.static:
        base = (out_video or args.input).with_suffix("")
        cmds_path = build_sendcmd(times, cx, cy, Path(f"{base}.crop.cmd"))

    vf = build_filter(cw, ch, x0, y0, ow, oh, cmds_path)

    if args.print_filter:
        print(vf)
        return

    out_video.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", str(args.input),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_video),
    ]
    print("→ renderizando")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr[-2000:], file=sys.stderr)
        sys.exit(1)

    meta_path = out_video.with_suffix(".reframe.json")
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"✓ {out_video}")
    print(f"  metadados: {meta_path}")


if __name__ == "__main__":
    main()

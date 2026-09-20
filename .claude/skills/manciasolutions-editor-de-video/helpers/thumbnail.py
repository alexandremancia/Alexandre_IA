"""Capa/thumbnail: acha o melhor frame e monta a arte com título.

Pontua frames por nitidez (variância do laplaciano), contraste, saturação e
presença de rosto, então compõe a capa com título em PIL. Exporta nos
formatos que as plataformas pedem.

Uso:
    python helpers/thumbnail.py final.mp4 --scan -o edit/verify/candidatos
    python helpers/thumbnail.py final.mp4 -o edit/capa.png --title "COMO EDITEI ISSO" --at 12.5
    python helpers/thumbnail.py final.mp4 -o edit/capa.png --title "3 ERROS" --subtitle "que todo mundo comete" --size youtube
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SIZES = {
    "youtube": (1280, 720),
    "vertical": (1080, 1920),
    "feed": (1080, 1350),
    "square": (1080, 1080),
}

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def find_font(explicit: str | None = None) -> str | None:
    if explicit and Path(explicit).exists():
        return explicit
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            return p
    return None


# Detector de rosto compartilhado com o reframe.py. Não duplicar: a API mudou
# entre OpenCV 4 (Haar) e 5 (YuNet), e manter duas cópias garante que uma delas
# vai ficar para trás — foi exatamente o que aconteceu aqui antes.
_FACE_DETECTOR = None
_FACE_READY = False


def has_face(pil_img) -> bool:
    """True se houver rosto no frame. False também quando não há detector."""
    global _FACE_DETECTOR, _FACE_READY
    if not _FACE_READY:
        _FACE_READY = True
        try:
            from reframe import make_face_detector
            _FACE_DETECTOR, _ = make_face_detector()
        except Exception:
            _FACE_DETECTOR = None
    if _FACE_DETECTOR is None:
        return False
    try:
        import cv2
        import numpy as np

        bgr = cv2.cvtColor(np.asarray(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
        return _FACE_DETECTOR(bgr) is not None
    except Exception:
        return False


def duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def grab(path: Path, t: float, out: Path) -> bool:
    proc = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path),
         "-frames:v", "1", str(out)],
        capture_output=True, text=True,
    )
    return proc.returncode == 0 and out.exists()


def score_frame(img_path: Path) -> dict:
    """Nitidez + contraste + saturação + rosto. Quanto maior, melhor a capa."""
    import numpy as np
    from PIL import Image

    img = Image.open(img_path).convert("RGB")
    small = img.resize((320, int(320 * img.height / img.width)))
    a = np.asarray(small).astype(np.float32)
    gray = a.mean(axis=2)

    # laplaciano 3x3 → foco
    lap = (
        -4 * gray[1:-1, 1:-1]
        + gray[:-2, 1:-1] + gray[2:, 1:-1]
        + gray[1:-1, :-2] + gray[1:-1, 2:]
    )
    sharpness = float(lap.var())
    contrast = float(gray.std())
    mx, mn = a.max(axis=2), a.min(axis=2)
    saturation = float(((mx - mn) / (mx + 1e-6)).mean())

    # Detecção numa escala maior que a das estatísticas: a 320px de largura um
    # rosto de plano médio fica com ~50px e passa despercebido pelo detector.
    # 720px é o menor tamanho em que o rosto sobrevive sem custar o scan inteiro.
    detect_w = 720
    detect_img = img if img.width <= detect_w else img.resize(
        (detect_w, max(1, int(detect_w * img.height / img.width))))
    faces = 1 if has_face(detect_img) else 0

    total = (
        min(sharpness / 400.0, 1.0) * 40
        + min(contrast / 70.0, 1.0) * 30
        + min(saturation / 0.45, 1.0) * 15
        + faces * 15
    )
    return {"sharpness": round(sharpness, 1), "contrast": round(contrast, 1),
            "saturation": round(saturation, 3), "faces": faces, "score": round(total, 1)}


def scan(path: Path, n: int, out_dir: Path) -> list[dict]:
    dur = duration(path)
    if dur <= 0:
        print("erro: duração inválida", file=sys.stderr)
        sys.exit(1)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            t = dur * (i + 0.5) / n
            tmp = Path(td) / f"f{i:03d}.png"
            if not grab(path, t, tmp):
                continue
            s = score_frame(tmp)
            s["t"] = round(t, 2)
            final = out_dir / f"cand_{s['score']:05.1f}_{t:07.2f}s.png"
            tmp.replace(final)
            s["file"] = str(final)
            results.append(s)
    results.sort(key=lambda r: -r["score"])
    return results


def wrap(draw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def compose(
    frame: Path,
    out: Path,
    size: tuple[int, int],
    title: str | None,
    subtitle: str | None,
    font_path: str | None,
    accent: str,
    darken: float,
    position: str,
) -> None:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont

    W, H = size
    img = Image.open(frame).convert("RGB")

    # cover: preenche sem distorcer
    scale = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    img = img.crop((left, top, left + W, top + H))

    if darken > 0:
        img = ImageEnhance.Brightness(img).enhance(1 - darken)
    img = ImageEnhance.Color(img).enhance(1.12)
    img = ImageEnhance.Contrast(img).enhance(1.08)

    if not title:
        img.save(out, quality=95)
        return

    draw = ImageDraw.Draw(img)
    fp = find_font(font_path)
    if not fp:
        print("aviso: nenhuma fonte encontrada — capa sai sem texto", file=sys.stderr)
        img.save(out, quality=95)
        return

    title_size = int(H * 0.13)
    sub_size = int(H * 0.055)
    font = ImageFont.truetype(fp, title_size)
    sub_font = ImageFont.truetype(fp, sub_size)

    margin = int(W * 0.06)
    max_w = W - 2 * margin
    lines = wrap(draw, title.upper(), font, max_w)

    # reduz até caber em no máximo 3 linhas
    while len(lines) > 3 and title_size > 24:
        title_size = int(title_size * 0.9)
        font = ImageFont.truetype(fp, title_size)
        lines = wrap(draw, title.upper(), font, max_w)

    line_h = int(title_size * 1.12)
    block_h = line_h * len(lines) + (int(sub_size * 1.4) if subtitle else 0)

    if position == "top":
        y = margin
    elif position == "center":
        y = (H - block_h) // 2
    else:
        y = H - block_h - margin

    stroke = max(3, title_size // 12)
    for ln in lines:
        w = draw.textlength(ln, font=font)
        x = (W - w) // 2
        draw.text((x, y), ln, font=font, fill=accent,
                  stroke_width=stroke, stroke_fill="#000000")
        y += line_h

    if subtitle:
        w = draw.textlength(subtitle, font=sub_font)
        draw.text(((W - w) // 2, y + int(sub_size * 0.2)), subtitle, font=sub_font,
                  fill="#FFFFFF", stroke_width=max(2, sub_size // 14), stroke_fill="#000000")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=95)


def main() -> None:
    ap = argparse.ArgumentParser(description="Gera capa/thumbnail a partir do vídeo")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--scan", action="store_true", help="Só procura os melhores frames")
    ap.add_argument("--n", type=int, default=24, help="Frames amostrados no scan")
    ap.add_argument("--at", type=float, default=None, help="Usa o frame deste instante (s)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--subtitle", default=None)
    ap.add_argument("--size", default="youtube", choices=list(SIZES))
    ap.add_argument("--accent", default="#FFD400", help="Cor do título")
    ap.add_argument("--font", default=None, help="Caminho para a fonte .ttf/.ttc")
    ap.add_argument("--darken", type=float, default=0.18, help="Escurecimento do fundo (0-1)")
    ap.add_argument("--position", default="bottom", choices=["top", "center", "bottom"])
    args = ap.parse_args()

    if not args.video.exists():
        print(f"erro: {args.video} não existe", file=sys.stderr)
        sys.exit(1)

    if args.scan:
        results = scan(args.video, args.n, args.output)
        print(f"\n── candidatos a capa ({len(results)}) ──")
        for r in results[:10]:
            print(f"  {r['score']:>5.1f}  {r['t']:>7.2f}s  nitidez {r['sharpness']:>7.1f}  "
                  f"contraste {r['contrast']:>5.1f}  rostos {r['faces']}")
        meta = args.output / "scan.json"
        meta.write_text(json.dumps(results, indent=2))
        print(f"\n✓ {args.output}  (melhor: {results[0]['t']}s)" if results else "nenhum frame")
        return

    with tempfile.TemporaryDirectory() as td:
        frame = Path(td) / "frame.png"
        if args.at is not None:
            t = args.at
        else:
            results = scan(args.video, args.n, Path(td) / "cands")
            if not results:
                print("erro: nenhum frame utilizável", file=sys.stderr)
                sys.exit(1)
            t = results[0]["t"]
            print(f"melhor frame automático: {t}s (score {results[0]['score']})")
        if not grab(args.video, t, frame):
            print(f"erro: não consegui extrair o frame em {t}s", file=sys.stderr)
            sys.exit(1)
        compose(frame, args.output, SIZES[args.size], args.title, args.subtitle,
                args.font, args.accent, args.darken, args.position)

    print(f"✓ {args.output}  ({SIZES[args.size][0]}x{SIZES[args.size][1]})")


if __name__ == "__main__":
    main()

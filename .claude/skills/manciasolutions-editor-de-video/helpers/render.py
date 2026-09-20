"""Render a video from an EDL.

Implements the HEURISTICS render pipeline in the correct order:

  1. Per-segment extract with color grade + 30ms audio fades baked in
  2. Lossless -c copy concat into base.mp4
  3. If overlays or subtitles: single filter graph that overlays animations
     (with PTS shift so frame 0 lands at the overlay window start)
     and applies `subtitles` filter LAST → final.mp4

Optionally builds a master SRT from the per-source transcripts + EDL
output-timeline offsets, applies the proven force_style (2-word
UPPERCASE chunks, Helvetica 18 Bold, MarginV=35).

Usage:
    python helpers/render.py <edl.json> -o final.mp4
    python helpers/render.py <edl.json> -o preview.mp4 --preview
    python helpers/render.py <edl.json> -o final.mp4 --build-subtitles
    python helpers/render.py <edl.json> -o final.mp4 --no-subtitles
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

try:
    from grade import get_preset, auto_grade_for_clip  # same directory
except Exception:
    def get_preset(name: str) -> str:
        return ""

    def auto_grade_for_clip(video, start=0.0, duration=None, verbose=False):  # type: ignore
        return "eq=contrast=1.03:saturation=0.98", {}


# -------- Subtitle style (bold-overlay, proven at 1920×1080 and 1080×1920) --
#
# MarginV is NOT taste — it is a platform safe-zone rule.
# TikTok / IG Reels / Shorts UI (caption, username, music, right-rail actions)
# covers roughly the bottom ~25–30% of a 1080×1920 frame. Captions placed near
# the bottom edge get clipped or obscured by the UI. libass auto-scales the
# render canvas relative to PlayResY=288, so MarginV=90 lands the caption
# baseline roughly 30% up from the bottom on any aspect — clear of the UI on
# every major vertical-video platform. Do not drop this below ~75 without a
# specific reason.
SUB_FORCE_STYLE = (
    "FontName=Helvetica,FontSize=18,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H00000000,"
    "BorderStyle=1,Outline=2,Shadow=0,"
    "Alignment=2,MarginV=90"
)

# -------- Helpers ------------------------------------------------------------


def run(cmd: list[str], quiet: bool = False) -> None:
    if not quiet:
        print(f"  $ {' '.join(str(c) for c in cmd[:6])}{' …' if len(cmd) > 6 else ''}")
    subprocess.run(cmd, check=True)


def resolve_grade_filter(grade_field: str | None) -> str:
    """The EDL's 'grade' field can be a preset name, a raw ffmpeg filter, or 'auto'.

    Returns the filter string to embed into the per-segment -vf chain.
    For 'auto', returns the sentinel "__AUTO__" which is resolved per-segment.
    """
    if not grade_field:
        return ""
    if grade_field == "auto":
        return "__AUTO__"
    # Preset names are short identifiers, filter strings contain '=' or ','.
    if re.fullmatch(r"[a-zA-Z0-9_\-]+", grade_field):
        try:
            return get_preset(grade_field)
        except KeyError:
            print(f"warning: unknown preset '{grade_field}', using as raw filter")
            return grade_field
    return grade_field


def resolve_path(maybe_path: str, base: Path) -> Path:
    """Resolve a path that may be absolute or relative to `base`."""
    p = Path(maybe_path)
    if p.is_absolute():
        return p
    return (base / p).resolve()


# -------- HDR → SDR tone mapping (HLG / PQ sources) --------------------------
#
# iPhone defaults to HLG HDR in Rec.2020 (and many mirrorless cameras ship PQ).
# If the source is HDR and we only downconvert bit depth (yuv420p10le → yuv420p)
# without tone-mapping, the output is 8-bit but still carries HLG/PQ transfer
# metadata. Players that honor the metadata (screen recorders, most social
# upload re-encodes) interpret 8-bit values in an HDR container and the result
# looks oversaturated / blown out. QuickTime on macOS can hide this locally —
# screen recording and uploaded renders cannot.
#
# Fix: detect HDR via color_transfer and prepend a zscale+tonemap chain to the
# vf graph so the output is clean Rec.709 SDR.

HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}  # PQ (HDR10) and HLG

TONEMAP_CHAIN = (
    "zscale=t=linear:npl=100,"
    "format=gbrpf32le,"
    "zscale=p=bt709,"
    "tonemap=tonemap=hable:desat=0,"
    "zscale=t=bt709:m=bt709:r=tv,"
    "format=yuv420p"
)


def is_hdr_source(video: Path) -> bool:
    """Return True if the source uses a PQ or HLG transfer function."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=color_transfer",
             "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip() in HDR_TRANSFERS
    except subprocess.CalledProcessError:
        return False


def is_portrait_source(video: Path) -> bool:
    """Return True if the displayed video is portrait, including rotation."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries",
             "stream=width,height:stream_side_data=rotation",
             "-of", "json", str(video)],
            capture_output=True, text=True, check=True,
        )
        streams = json.loads(out.stdout).get("streams") or []
        if not streams:
            return False
        stream = streams[0]
        w, h = int(stream["width"]), int(stream["height"])

        # ffmpeg autorotates display-matrix side data before applying filters.
        # Swap coded dimensions for quarter-turns so the scale axis is selected
        # from the dimensions the filter actually sees. A plain metadata tag is
        # intentionally ignored because it does not guarantee autorotation.
        rotation = 0
        for side_data in stream.get("side_data_list") or []:
            if side_data.get("rotation") is not None:
                rotation = side_data["rotation"]
                break
        if int(round(float(rotation))) % 360 in (90, 270):
            w, h = h, w
        return h > w
    except (
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        OSError,
        OverflowError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return False


def parse_fps(value: str) -> str:
    """Validate and canonicalize an ffmpeg frame rate."""
    text = value.strip()
    if len(text) > 32 or not re.fullmatch(
        r"(?:[0-9]+(?:\.[0-9]+)?|[0-9]+/[0-9]+)", text
    ):
        raise argparse.ArgumentTypeError(
            "FPS must be a positive number or rational, e.g. 30 or 30000/1001"
        )
    try:
        rate = Fraction(text)
    except (ValueError, ZeroDivisionError) as exc:
        raise argparse.ArgumentTypeError(
            "FPS must be a positive number or rational, e.g. 30 or 30000/1001"
        ) from exc
    if rate <= 0:
        raise argparse.ArgumentTypeError("FPS must be greater than zero")
    # FFmpeg stores video rates as AVRational (signed 32-bit components).
    # Bounding the reduced fraction keeps every accepted canonical value safe
    # for ffmpeg and makes parse_fps(parse_fps(value)) idempotent.
    max_component = 2_147_483_647
    if rate.numerator > max_component or rate.denominator > max_component:
        raise argparse.ArgumentTypeError("FPS precision or magnitude is too large")
    return f"{rate.numerator}/{rate.denominator}"


def probe_source_fps(video: Path) -> str | None:
    """Return an ffmpeg-ready source rate, preferring the average frame rate.

    ``avg_frame_rate`` represents the observed average and is the better default
    for variable-frame-rate inputs. ``r_frame_rate`` remains a fallback for
    streams where the average is unavailable. Values are normalized to an exact
    rational so rates such as ``30000/1001`` survive without rounding.
    """
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=avg_frame_rate,r_frame_rate",
             "-of", "json", str(video)],
            capture_output=True, text=True, check=True,
        )
        streams = json.loads(out.stdout).get("streams") or []
        if not streams:
            return None
        for field in ("avg_frame_rate", "r_frame_rate"):
            value = streams[0].get(field)
            if value and value != "0/0":
                try:
                    return parse_fps(value)
                except argparse.ArgumentTypeError:
                    continue
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
        return None
    return None


# -------- Per-segment extraction (Rule 2 + Rule 3) --------------------------


def probe_source_size(video: Path) -> tuple[int, int] | None:
    """Largura e altura da fonte. O zoompan exige tamanho de saída explícito."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(video)],
        capture_output=True, text=True,
    )
    try:
        w, h = proc.stdout.strip().split("x")
        return int(w), int(h)
    except ValueError:
        return None


def parse_punch(punch) -> tuple[float, float, float, float] | None:
    """Normaliza o campo `punch` do EDL para (z_inicial, z_final, foco_x, foco_y).

    Aceita:
      punch: 1.15                                → zoom fixo de 15%
      punch: {"from": 1.0, "to": 1.12}           → push lento ao longo do segmento
      punch: {"zoom": 1.2, "x": 0.5, "y": 0.35}  → zoom fixo com foco fora do centro

    x/y são normalizados (0 = esquerda/topo, 1 = direita/base, 0.5 = centro).
    Devolve None quando não há punch a aplicar.
    """
    if not punch:
        return None
    if isinstance(punch, (int, float)):
        z_from = z_to = float(punch)
        fx = fy = 0.5
    else:
        z_from = float(punch.get("from", punch.get("zoom", 1.0)))
        z_to = float(punch.get("to", punch.get("zoom", z_from)))
        fx = float(punch.get("x", 0.5))
        fy = float(punch.get("y", 0.5))

    if z_from <= 0 or z_to <= 0:
        raise ValueError(f"punch inválido: {punch}")
    if abs(z_from - 1.0) < 1e-6 and abs(z_to - 1.0) < 1e-6:
        return None
    return z_from, z_to, fx, fy


def build_punch_filter(punch, seg_duration: float,
                       src_size: tuple[int, int] | None = None,
                       fps: float = 30.0) -> str:
    """Filtro de punch-in, aplicado ANTES do scale (na resolução da fonte).

    Zoom fixo vira `crop`: barato, sem reamostragem extra.

    Rampa vira `zoompan`. O `crop` NÃO serve para rampa: as dimensões de saída
    dele são fixadas na configuração do filtro e não podem variar quadro a
    quadro (e nesta build ele nem aceita a opção `eval`). O `zoompan` mantém o
    tamanho de saída constante em `s` e varia o zoom por frame, que é
    exatamente o que um push precisa. Ele exige `s` explícito — por isso
    `src_size`; sem ele, a rampa cai para o zoom médio em `crop`, o que é pior
    mas não quebra.

    Nenhuma expressão usa vírgula: vírgula dentro de -vf separa filtros e
    quebraria o grafo em silêncio.
    """
    parsed = parse_punch(punch)
    if parsed is None:
        return ""
    z_from, z_to, fx, fy = parsed

    def static(z: float) -> str:
        return (
            f"crop=w='floor(iw/{z:.6f}/2)*2':h='floor(ih/{z:.6f}/2)*2':"
            f"x='(iw-ow)*{fx:.4f}':y='(ih-oh)*{fy:.4f}'"
        )

    if abs(z_from - z_to) < 1e-6:
        return static(z_from)

    if src_size is None:
        return static((z_from + z_to) / 2)

    w, h = src_size
    total = max(1, int(round(max(seg_duration, 1e-3) * fps)) - 1)
    zexpr = f"{z_from:.6f}+({z_to - z_from:.6f})*on/{total}"
    return (
        f"zoompan=z='{zexpr}':x='(iw-iw/zoom)*{fx:.4f}':y='(ih-ih/zoom)*{fy:.4f}':"
        f"d=1:s={w}x{h}:fps={fps:g}"
    )


def build_atempo_chain(speed: float) -> str:
    """atempo só aceita 0.5–2.0 por instância; fora disso, encadeia."""
    if abs(speed - 1.0) < 1e-6:
        return ""
    parts = []
    remaining = speed
    while remaining > 2.0:
        parts.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        parts.append("atempo=0.5")
        remaining /= 0.5
    parts.append(f"atempo={remaining:.6f}")
    return ",".join(parts)


def extract_segment(
    source: Path,
    seg_start: float,
    duration: float,
    grade_filter: str,
    out_path: Path,
    preview: bool = False,
    draft: bool = False,
    rate: str | None = None,
    speed: float = 1.0,
    punch=None,
    out_size: tuple[int, int] | None = None,
) -> None:
    """Extract a cut range as its own MP4 with grade + 30ms audio fades baked in.

    `-ss` before `-i` for fast accurate seeking. Scale to 1080p from 4K.
    Portrait sources (height > width) are scaled by height to preserve orientation.

    Quality ladder:
      - final (default): 1080p libx264 fast CRF 20
      - preview:         1080p libx264 medium CRF 22 (evaluable for QC)
      - draft:           720p libx264 ultrafast CRF 28 (cut-point check only)
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # UMA geometria para o render inteiro, com pillarbox/letterbox quando a
    # fonte não casa.
    #
    # Escalar por orientação de CADA fonte (o que o upstream fazia) quebra o
    # concat quando o EDL mistura horizontal e vertical: os segmentos saem
    # 1920x1080 e 1080x1920, o `-c copy` aceita sem reclamar, e o arquivo passa
    # a trocar de resolução no meio. O estrago aparece longe daqui — a legenda
    # renderiza esticada nos segmentos de orientação diferente, e a geometria
    # dos overlays vai para o lugar errado. `setsar=1` completa o serviço: o
    # crop do punch deixa SAR quebrado (7713:7712) e o concat fica heterogêneo
    # de novo, agora no pixel aspect em vez da resolução.
    if out_size is not None:
        tw, th = out_size
    else:
        portrait = is_portrait_source(source)
        base = 1280 if draft else 1920
        tw, th = (base * 9 // 16, base) if portrait else (base, base * 9 // 16)
    scale = (f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
             f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")

    vf_parts: list[str] = []
    if is_hdr_source(source):
        vf_parts.append(TONEMAP_CHAIN)
    # Punch antes do scale: recorta na resolução da fonte, o scale normaliza depois.
    punch_filter = ""
    if punch:
        try:
            fps_val = float(Fraction(rate)) if rate else (
                float(Fraction(probe_source_fps(source) or "30")))
        except (ValueError, ZeroDivisionError):
            fps_val = 30.0
        punch_filter = build_punch_filter(
            punch, duration, src_size=probe_source_size(source), fps=fps_val)
    if punch_filter:
        vf_parts.append(punch_filter)
    vf_parts.append(scale)
    if grade_filter:
        vf_parts.append(grade_filter)
    # Speed ramp: setpts comprime o tempo do vídeo, atempo o do áudio.
    if abs(speed - 1.0) > 1e-6:
        vf_parts.append(f"setpts=PTS/{speed:.6f}")
    vf = ",".join(vf_parts)

    # A duração de SAÍDA é o que conta para o fade — com speed != 1 ela muda.
    out_duration = duration / speed if speed else duration

    # 30ms audio fades at both edges (Rule 3) — prevent pops
    fade_out_start = max(0.0, out_duration - 0.03)
    af_parts = []
    tempo = build_atempo_chain(speed)
    if tempo:
        af_parts.append(tempo)
    af_parts.append(f"afade=t=in:st=0:d=0.03")
    af_parts.append(f"afade=t=out:st={fade_out_start:.3f}:d=0.03")
    af = ",".join(af_parts)

    if draft:
        preset, crf = "ultrafast", "28"
    elif preview:
        preset, crf = "medium", "22"
    else:
        preset, crf = "fast", "20"

    # Frame rate: use the rate the caller resolved once for the whole render
    # (every segment must share it — concat -c copy in Rule 2 requires a uniform
    # frame rate). When called standalone with no rate, preserve this source's
    # own rate; fall back to 24 only if it can't be probed.
    out_rate = rate if rate is not None else (probe_source_fps(source) or "24")

    # -ss E -t antes de -i: os dois limitam a ENTRADA, em segundos da FONTE.
    #
    # Isto não é estilo, é correção. Com -t depois de -i ele limita a SAÍDA:
    # sob `setpts=PTS/1.2` o ffmpeg passa a ler 1.2x mais material da fonte para
    # encher a duração pedida, e o segmento sai com o comprimento original em vez
    # de acelerado. O corte cobre mais texto do que o EDL diz, a timeline não
    # encurta, e nada acusa erro. O -t da saída abaixo é o cinto de segurança:
    # fixa a duração final exatamente em duration/speed.
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{seg_start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(source),
        "-t", f"{out_duration:.3f}",
        "-vf", vf,
        "-af", af,
        "-c:v", "libx264", "-preset", preset, "-crf", crf,
        "-pix_fmt", "yuv420p", "-r", out_rate,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        # ffmpeg silenciado é ffmpeg indepurável: mostre o grafo e o erro real.
        print(f"\nffmpeg falhou ({proc.returncode}) em {out_path.name}", file=sys.stderr)
        print(f"  -vf {vf}", file=sys.stderr)
        print(f"  -af {af}", file=sys.stderr)
        print((proc.stderr or "")[-1500:], file=sys.stderr)
        raise subprocess.CalledProcessError(proc.returncode, cmd, stderr=proc.stderr)


def resolve_output_size(edl: dict, edit_dir: Path, explicit: str | None,
                        draft: bool = False) -> tuple[int, int]:
    """Uma geometria de saída para o render inteiro (Regra Dura 2).

    `--size` manda. Sem ele, herda a orientação da PRIMEIRA fonte, que é o
    comportamento esperado em um EDL de orientação única. Quando as fontes
    misturam orientações, avisa: quem não escolher vai receber pillarbox, e é
    melhor saber disso antes de renderizar 20 minutos.
    """
    if explicit:
        try:
            w, h = explicit.lower().replace("×", "x").split("x")
            w, h = int(w), int(h)
        except ValueError:
            sys.exit(f"--size inválido: {explicit!r} (esperado LARGURAxALTURA, ex. 1080x1920)")
        if w % 2 or h % 2:
            sys.exit(f"--size {explicit}: largura e altura têm de ser pares (yuv420p)")
        return w, h

    ranges = edl.get("ranges") or []
    if not ranges:
        return (1280, 720) if draft else (1920, 1080)

    sources = edl["sources"]
    orientations = set()
    for r in ranges:
        src = resolve_path(sources[r["source"]], edit_dir)
        orientations.add("portrait" if is_portrait_source(src) else "landscape")

    first = resolve_path(sources[ranges[0]["source"]], edit_dir)
    portrait = is_portrait_source(first)
    base = 1280 if draft else 1920
    size = (base * 9 // 16, base) if portrait else (base, base * 9 // 16)

    if len(orientations) > 1:
        print(f"  aviso: o EDL mistura fontes horizontais e verticais. Saída fixada em "
              f"{size[0]}x{size[1]} (da primeira fonte); o que não casar recebe barras.")
        print(f"         Para escolher, passe --size (ex. --size 1080x1920).")
    return size


def extract_all_segments(
    edl: dict,
    edit_dir: Path,
    preview: bool,
    draft: bool = False,
    fps: str | None = None,
    out_size: tuple[int, int] | None = None,
) -> list[Path]:
    """Extract every EDL range into edit_dir/clips_graded/seg_NN.mp4.
    Returns the ordered list of segment paths.

    If the EDL `grade` is "auto", analyze each segment range with
    `auto_grade_for_clip` and apply a per-segment subtle correction.
    Otherwise, apply the same preset/raw filter to every segment.
    """
    resolved = resolve_grade_filter(edl.get("grade"))
    is_auto = resolved == "__AUTO__"
    handles = transition_handles(edl)
    clips_dir = edit_dir / (
        "clips_draft" if draft else ("clips_preview" if preview else "clips_graded")
    )
    clips_dir.mkdir(parents=True, exist_ok=True)

    ranges = edl["ranges"]
    sources = edl["sources"]

    # Resolve ONE output frame rate for the entire render and apply it to every
    # segment. The lossless concat (Rule 2, `-c copy`) requires all segments to
    # share a frame rate; probing per-segment would diverge for multi-source
    # EDLs that mix rates (e.g. a 30fps and a 60fps source) and break the concat.
    # Explicit --fps wins; otherwise preserve the first source's rate.
    if fps is not None:
        out_rate = parse_fps(str(fps))
    elif ranges:
        first_src = resolve_path(sources[ranges[0]["source"]], edit_dir)
        out_rate = probe_source_fps(first_src) or "24"
    else:
        out_rate = "24"

    seg_paths: list[Path] = []
    geom = f"{out_size[0]}x{out_size[1]}" if out_size else "por fonte"
    print(f"extracting {len(ranges)} segment(s) → {clips_dir.name}/  @ {out_rate} fps"
          f"{' (forced)' if fps is not None else ' (from source)'}, {geom}")
    if is_auto:
        print("  (auto-grade per segment: analyzing each range)")
    for i, r in enumerate(ranges):
        src_name = r["source"]
        src_path = resolve_path(sources[src_name], edit_dir)
        start = float(r["start"])
        end = float(r["end"])
        duration = end - start
        out_path = clips_dir / f"seg_{i:02d}_{src_name}.mp4"

        if is_auto:
            seg_filter, _stats = auto_grade_for_clip(src_path, start=start, duration=duration, verbose=False)
        else:
            seg_filter = resolved

        # Handles para transição: a transição consome material EXTRA de cada
        # lado da junção, não o corte em si. Sem isso, cada transição encurtaria
        # a timeline e desalinharia legenda e overlays (Regras Duras 5 e 13).
        handle_in = handles.get(i, (0.0, 0.0))[0]
        handle_out = handles.get(i, (0.0, 0.0))[1]
        real_start = start - handle_in
        if real_start < 0:
            print(f"        aviso: sem material antes de {start:.2f}s para o handle "
                  f"de {handle_in:.2f}s — transição vai encurtar a timeline aqui")
            handle_in = start
            real_start = 0.0
        real_duration = duration + handle_in + handle_out

        speed = float(r.get("speed", 1.0)) or 1.0
        punch = r.get("punch")

        note = r.get("beat") or r.get("note") or ""
        extras = []
        if speed != 1.0:
            extras.append(f"speed {speed}x")
        if punch:
            extras.append(f"punch {punch}")
        if handle_in or handle_out:
            extras.append(f"handles +{handle_in:.2f}/{handle_out:.2f}")
        suffix = ("  [" + ", ".join(extras) + "]") if extras else ""
        print(f"  [{i:02d}] {src_name}  {start:7.2f}-{end:7.2f}  ({duration:5.2f}s)  {note}{suffix}")
        if is_auto:
            print(f"        grade: {seg_filter or '(none)'}")
        extract_segment(src_path, real_start, real_duration, seg_filter, out_path,
                        preview=preview, draft=draft, rate=out_rate,
                        speed=speed, punch=punch, out_size=out_size)
        seg_paths.append(out_path)

    return seg_paths


# -------- Transições (Regra Dura 13) ----------------------------------------


def transition_handles(edl: dict) -> dict[int, tuple[float, float]]:
    """Quanto de material extra cada segmento precisa em cada borda.

    Uma transição de d segundos entre i e i+1 pede d/2 de cauda em i e d/2 de
    cabeça em i+1. Assim o xfade sobrepõe SÓ o material extra e a duração
    visível da timeline não muda.
    """
    out: dict[int, tuple[float, float]] = {}
    for tr in edl.get("transitions", []) or []:
        i = int(tr["after"])
        d = float(tr.get("duration", 0.4))
        a_in, a_out = out.get(i, (0.0, 0.0))
        out[i] = (a_in, a_out + d / 2)
        b_in, b_out = out.get(i + 1, (0.0, 0.0))
        out[i + 1] = (b_in + d / 2, b_out)
    return out


def probe_duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


XFADE_TYPES = {
    "fade", "fadeblack", "fadewhite", "dissolve", "wipeleft", "wiperight",
    "wipeup", "wipedown", "slideleft", "slideright", "slideup", "slidedown",
    "circleopen", "circleclose", "circlecrop", "rectcrop", "radial",
    "smoothleft", "smoothright", "smoothup", "smoothdown", "pixelize",
    "hlslice", "vuslice", "distance", "fadegrays", "squeezeh", "squeezev",
    "zoomin", "hblur", "diagtl", "diagtr", "diagbl", "diagbr",
}


def apply_transitions(seg_paths: list[Path], edl: dict, edit_dir: Path,
                      preview: bool = False, draft: bool = False,
                      rate: str | None = None) -> list[Path]:
    """Funde pares marcados com xfade; o resto segue para o concat lossless.

    Regra Dura 13: xfade re-encoda os dois segmentos envolvidos. Por isso ele
    só toca as junções explicitamente marcadas no EDL — nunca a timeline
    inteira, que é o que um filtergraph único faria.
    """
    transitions = edl.get("transitions") or []
    if not transitions:
        return seg_paths

    by_index = {int(t["after"]): t for t in transitions}
    crf = "28" if draft else ("22" if preview else "20")
    preset = "ultrafast" if draft else ("medium" if preview else "fast")
    out_rate = rate or "30"

    merged: list[Path] = []
    i = 0
    while i < len(seg_paths):
        tr = by_index.get(i)
        if tr is None or i + 1 >= len(seg_paths):
            merged.append(seg_paths[i])
            i += 1
            continue

        d = float(tr.get("duration", 0.4))
        kind = tr.get("type", "fade")
        if kind not in XFADE_TYPES:
            print(f"  aviso: transição '{kind}' não existe no xfade — usando 'fade'. "
                  f"Tipos: {', '.join(sorted(XFADE_TYPES))}")
            kind = "fade"

        a, b = seg_paths[i], seg_paths[i + 1]
        dur_a = probe_duration(a)
        offset = max(0.0, dur_a - d)
        out = a.with_name(a.stem + f"_x{kind}.mp4")

        graph = (
            f"[0:v][1:v]xfade=transition={kind}:duration={d:.3f}:offset={offset:.3f}[v];"
            f"[0:a][1:a]acrossfade=d={d:.3f}:c1=tri:c2=tri[a]"
        )
        print(f"  transição {kind} {d:.2f}s entre [{i:02d}] e [{i+1:02d}] (offset {offset:.2f}s)")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(a), "-i", str(b),
             "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
             "-c:v", "libx264", "-preset", preset, "-crf", crf,
             "-pix_fmt", "yuv420p", "-r", out_rate,
             "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(out)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        merged.append(out)
        i += 2

    return merged


# -------- Lossless concat ----------------------------------------------------


def concat_segments(segment_paths: list[Path], out_path: Path, edit_dir: Path) -> None:
    """Lossless concat via the concat demuxer. No re-encode."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_list = edit_dir / "_concat.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in segment_paths))

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"concat → {out_path.name}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    concat_list.unlink(missing_ok=True)


# -------- Master SRT (Rule 5) ------------------------------------------------


PUNCT_BREAK = set(".,!?;:")


def _srt_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _words_in_range(transcript: dict, t_start: float, t_end: float) -> list[dict]:
    out: list[dict] = []
    for w in transcript.get("words", []):
        if w.get("type") != "word":
            continue
        ws = w.get("start")
        we = w.get("end")
        if ws is None or we is None:
            continue
        if we <= t_start or ws >= t_end:
            continue
        out.append(w)
    return out


def build_master_srt(edl: dict, edit_dir: Path, out_path: Path) -> None:
    """Build an output-timeline SRT from per-source transcripts.

    - 2-word chunks (break on any punctuation in between)
    - UPPERCASE text
    - Output times computed as word.start - segment_start + segment_offset
    """
    transcripts_dir = edit_dir / "transcripts"
    sources = edl["sources"]

    entries: list[tuple[float, float, str]] = []
    seg_offset = 0.0

    for r in edl["ranges"]:
        src_name = r["source"]
        seg_start = float(r["start"])
        seg_end = float(r["end"])
        seg_duration = seg_end - seg_start

        tr_path = transcripts_dir / f"{src_name}.json"
        if not tr_path.exists():
            print(f"  no transcript for {src_name}, skipping captions for this segment")
            seg_offset += seg_duration
            continue

        transcript = json.loads(tr_path.read_text())
        words_in_seg = _words_in_range(transcript, seg_start, seg_end)

        # Group into 2-word chunks, break on punctuation
        chunks: list[list[dict]] = []
        current: list[dict] = []
        for w in words_in_seg:
            text = (w.get("text") or "").strip()
            if not text:
                continue
            current.append(w)
            # Break if the current text ends in punctuation or we hit 2 words
            ends_in_punct = bool(text) and text[-1] in PUNCT_BREAK
            if len(current) >= 2 or ends_in_punct:
                chunks.append(current)
                current = []
        if current:
            chunks.append(current)

        for chunk in chunks:
            local_start = max(seg_start, chunk[0].get("start", seg_start))
            local_end = min(seg_end, chunk[-1].get("end", seg_end))
            out_start = max(0.0, local_start - seg_start) + seg_offset
            out_end = max(0.0, local_end - seg_start) + seg_offset
            if out_end <= out_start:
                out_end = out_start + 0.4
            text = " ".join((w.get("text") or "").strip() for w in chunk)
            text = re.sub(r"\s+", " ", text).strip()
            # Strip trailing punctuation for cleaner uppercase look
            text = text.rstrip(",;:")
            text = text.upper()
            entries.append((out_start, out_end, text))

        seg_offset += seg_duration

    # Sort and write as SRT
    entries.sort(key=lambda e: e[0])
    lines: list[str] = []
    for i, (a, b, t) in enumerate(entries, start=1):
        lines.append(str(i))
        lines.append(f"{_srt_timestamp(a)} --> {_srt_timestamp(b)}")
        lines.append(t)
        lines.append("")
    out_path.write_text("\n".join(lines))
    print(f"master SRT → {out_path.name} ({len(entries)} cues)")


# -------- Loudness normalization (social-ready audio) -----------------------


# Social-media standard: -14 LUFS integrated, -1 dBTP peak, LRA 11 LU.
# Matches YouTube / Instagram / TikTok / X / LinkedIn normalization targets.
LOUDNORM_I = -14.0
# -1.5 e não -1.0: o loudnorm acerta o teto com precisão no sinal descomprimido,
# mas o AAC que vem depois faz overshoot. Medido neste repo, mirando TP=-1:
#
#     em PCM            -1.00 dBTP   (exato)
#     AAC 128k          -0.62 dBTP
#     AAC 192k          +0.30 dBTP   (acima de 0 — clipa no player)
#     mirando TP=-1.5   -1.05 dBTP   (chega onde se queria)
#
# Meio decibel de margem custa meio decibel de volume e evita distorção na
# reprodução. Plataforma nenhuma recompensa entregar mais alto: todas
# normalizam para perto de -14 LUFS de qualquer jeito.
LOUDNORM_TP = -1.5
LOUDNORM_LRA = 11.0


def measure_loudness(video_path: Path) -> dict[str, str] | None:
    """Run ffmpeg loudnorm first pass and parse the JSON measurement.

    Returns a dict with measured_i, measured_tp, measured_lra, measured_thresh,
    target_offset, or None if measurement failed.
    """
    filter_str = (
        f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA}:print_format=json"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(video_path),
        "-af", filter_str,
        "-vn", "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    # loudnorm prints the JSON to stderr at the end of the run
    stderr = proc.stderr

    # Find the JSON block — loudnorm output contains a `{ ... }` block
    start = stderr.rfind("{")
    end = stderr.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        data = json.loads(stderr[start : end + 1])
    except json.JSONDecodeError:
        return None
    needed = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if not needed.issubset(data.keys()):
        return None
    return data


def apply_loudnorm_two_pass(
    input_path: Path,
    output_path: Path,
    preview: bool = False,
) -> bool:
    """Run two-pass loudnorm on input_path, write normalized copy to output_path.

    Returns True on success, False if measurement failed (caller should fall
    back to copying the input unchanged).

    In preview mode, skips the measurement pass and uses a one-pass approximation
    for speed. Final mode always does the proper two-pass.
    """
    if preview:
        # One-pass approximation — faster, slightly less accurate.
        filter_str = f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA}"
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-nostats",
            "-i", str(input_path),
            "-c:v", "copy",
            "-af", filter_str,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(output_path),
        ]
        print(f"  loudnorm (1-pass preview) → {output_path.name}")
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True

    # Full two-pass
    print(f"  loudnorm pass 1: measuring {input_path.name}")
    measurement = measure_loudness(input_path)
    if measurement is None:
        print("  loudnorm measurement failed — falling back to 1-pass")
        return apply_loudnorm_two_pass(input_path, output_path, preview=True)

    print(f"    measured: I={measurement['input_i']} LUFS  "
          f"TP={measurement['input_tp']}  LRA={measurement['input_lra']}")

    filter_str = (
        f"loudnorm=I={LOUDNORM_I}:TP={LOUDNORM_TP}:LRA={LOUDNORM_LRA}"
        f":measured_I={measurement['input_i']}"
        f":measured_TP={measurement['input_tp']}"
        f":measured_LRA={measurement['input_lra']}"
        f":measured_thresh={measurement['input_thresh']}"
        f":offset={measurement['target_offset']}"
        f":linear=true"
    )
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-nostats",
        "-i", str(input_path),
        "-c:v", "copy",
        "-af", filter_str,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(output_path),
    ]
    print(f"  loudnorm pass 2: normalizing → {output_path.name}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    return True


# -------- Final compositing (Rule 1 + Rule 4) -------------------------------


def warn_subtitle_resolution(subs_path: Path, out_size: tuple[int, int]) -> None:
    """Confere se o PlayRes do .ass casa com a geometria do render."""
    play_x = play_y = None
    for line in subs_path.read_text(errors="ignore").splitlines():
        if line.startswith("PlayResX:"):
            play_x = int(line.split(":", 1)[1].strip() or 0)
        elif line.startswith("PlayResY:"):
            play_y = int(line.split(":", 1)[1].strip() or 0)
        elif line.startswith("[Events]"):
            break
    if not play_x or not play_y:
        return
    if (play_x, play_y) != out_size:
        print(f"  aviso: {subs_path.name} foi desenhada para {play_x}x{play_y}, "
              f"mas a saída é {out_size[0]}x{out_size[1]}.")
        print(f"         A fonte vai sair de tamanho errado. Regenere com:  "
              f"captions.py ... --res {out_size[0]}x{out_size[1]}")


def build_final_composite(
    base_path: Path,
    overlays: list[dict],
    subtitles_path: Path | None,
    out_path: Path,
    edit_dir: Path,
    rate: str | None = None,
) -> None:
    """Final pass: base → overlays (PTS-shifted) → subtitles LAST → out.

    If there are no overlays and no subtitles, just copy base to out.
    """
    has_overlays = bool(overlays)
    has_subs = subtitles_path is not None and subtitles_path.exists()

    if not has_overlays and not has_subs:
        # Nothing to do — just rename/copy base to final name
        run(["ffmpeg", "-y", "-i", str(base_path), "-c", "copy", str(out_path)], quiet=True)
        return

    inputs: list[str] = ["-i", str(base_path)]
    for ov in overlays:
        ov_path = resolve_path(ov["file"], edit_dir)
        inputs += ["-i", str(ov_path)]

    filter_parts: list[str] = []
    # PTS-shift every overlay so its frame 0 lands at start_in_output
    for idx, ov in enumerate(overlays, start=1):
        t = float(ov["start_in_output"])
        filter_parts.append(f"[{idx}:v]setpts=PTS-STARTPTS+{t}/TB[a{idx}]")

    # Chain overlays on top of base
    current = "[0:v]"
    for idx, ov in enumerate(overlays, start=1):
        t = float(ov["start_in_output"])
        dur = float(ov["duration"])
        end = t + dur
        next_label = f"[v{idx}]"
        # Posição do overlay. Sem x/y declarados, ffmpeg ancora em 0:0 — e um
        # overlay de quadro inteiro por cima da faixa de legenda a esconde sem
        # erro nenhum (Regra Dura 1). Declarar y é o que permite ao qc.py
        # provar que não há colisão.
        x = ov.get("x", 0)
        y = ov.get("y", 0)
        pos = f"x={x}:y={y}:"
        filter_parts.append(
            f"{current}[a{idx}]overlay={pos}enable='between(t,{t:.3f},{end:.3f})'{next_label}"
        )
        current = next_label

    # Subtitles LAST — Rule 1
    if has_subs:
        subs_abs = str(subtitles_path.resolve()).replace(":", r"\:").replace("'", r"\'")
        if subtitles_path.suffix.lower() == ".ass":
            # .ass já carrega o próprio estilo (fonte, cor, karaokê, margens).
            # Passar force_style aqui sobrescreveria o que o captions.py desenhou.
            filter_parts.append(f"{current}ass='{subs_abs}'[outv]")
        else:
            filter_parts.append(
                f"{current}subtitles='{subs_abs}':force_style='{SUB_FORCE_STYLE}'[outv]"
            )
        out_label = "[outv]"
    else:
        # Rename the last overlay output to [outv] for consistency
        if has_overlays:
            filter_parts.append(f"{current}null[outv]")
            out_label = "[outv]"
        else:
            out_label = "[0:v]"

    filter_complex = ";".join(filter_parts)

    # O concat demuxer costuma deixar r_frame_rate quebrado (ex. 179/6 em vez de
    # 30/1): a junção entre dois segmentos cria um delta de timestamp diferente
    # do resto, e o arquivo passa a ser tecnicamente VFR. Como este passe já
    # recodifica, é aqui que se conserta — forçar CFR depois custaria mais um
    # encode. Sem overlay nem legenda não há passe nenhum, e aí não há o que
    # consertar sem recodificar à toa.
    rate_opts = ["-fps_mode", "cfr", "-r", rate] if rate else []

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", out_label,
        "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p",
        *rate_opts,
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(out_path),
    ]
    print(f"compositing → {out_path.name}")
    print(f"  overlays: {len(overlays)}, subtitles: {'yes' if has_subs else 'no'}")
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


# -------- Main ---------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="Render a video from an EDL")
    ap.add_argument("edl", type=Path, help="Path to edl.json")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output video path")
    ap.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: 1080p, medium, CRF 22 — evaluable for QC, faster than final.",
    )
    ap.add_argument(
        "--draft",
        action="store_true",
        help="Draft mode: 720p, ultrafast, CRF 28 — cut-point verification only.",
    )
    ap.add_argument(
        "--build-subtitles",
        action="store_true",
        help="Build master.srt from transcripts + EDL offsets before compositing",
    )
    ap.add_argument(
        "--no-subtitles",
        action="store_true",
        help="Skip subtitles even if the EDL references one",
    )
    ap.add_argument(
        "--no-loudnorm",
        action="store_true",
        help="Skip audio loudness normalization. Default is on (-14 LUFS, -1 dBTP, LRA 11).",
    )
    ap.add_argument(
        "--size",
        default=None,
        help="Resolução de saída, ex. 1080x1920. Padrão: orientação da primeira fonte. "
             "Vale para todos os segmentos — o que não casar recebe barras.",
    )
    ap.add_argument(
        "--fps",
        type=parse_fps,
        default=None,
        help="Output frame rate. Default: preserve the source's frame rate "
             "(falls back to 24 if it can't be probed). Pass e.g. --fps 30 or "
             "--fps 30000/1001 to force.",
    )
    args = ap.parse_args()

    edl_path = args.edl.resolve()
    if not edl_path.exists():
        sys.exit(f"edl not found: {edl_path}")

    edl = json.loads(edl_path.read_text())
    edit_dir = edl_path.parent
    out_path = args.output.resolve()

    # 1. Extract per-segment (auto-grade per range if EDL grade is "auto")
    out_size = resolve_output_size(edl, edit_dir, args.size, draft=args.draft)
    segment_paths = extract_all_segments(
        edl, edit_dir, preview=args.preview, draft=args.draft, fps=args.fps,
        out_size=out_size,
    )

    # Uma taxa para todo o render: o concat -c copy exige que os segmentos
    # compartilhem frame rate (Regra Dura 2), e o passe final a usa para
    # devolver o arquivo a CFR.
    out_rate = args.fps or (probe_source_fps(
        resolve_path(edl["sources"][edl["ranges"][0]["source"]], edit_dir)) or "30"
    ) if edl.get("ranges") else None

    # 1b. Transições marcadas (re-encoda só os pares envolvidos, Regra Dura 13)
    if edl.get("transitions"):
        segment_paths = apply_transitions(
            segment_paths, edl, edit_dir,
            preview=args.preview, draft=args.draft, rate=out_rate,
        )

    # 2. Concat → base
    if args.draft:
        base_name = "base_draft.mp4"
    elif args.preview:
        base_name = "base_preview.mp4"
    else:
        base_name = "base.mp4"
    base_path = edit_dir / base_name
    concat_segments(segment_paths, base_path, edit_dir)

    # 3. Subtitles: build if requested, resolve final path
    subs_path: Path | None = None
    if not args.no_subtitles:
        if args.build_subtitles:
            subs_path = edit_dir / "master.srt"
            build_master_srt(edl, edit_dir, subs_path)
        elif edl.get("subtitles"):
            subs_path = resolve_path(edl["subtitles"], edit_dir)
            if not subs_path.exists():
                print(f"warning: subtitles path in EDL does not exist: {subs_path}")
                subs_path = None

    # A legenda .ass carrega a resolução em que foi desenhada. Aplicá-la sobre
    # outra geometria faz o libass reescalar a fonte, e a legenda sai de tamanho
    # errado — sem erro nenhum, só feio.
    if subs_path is not None and subs_path.suffix.lower() == ".ass":
        warn_subtitle_resolution(subs_path, out_size)

    # 4. Composite (overlays + subtitles LAST) → intermediate (pre-loudnorm) path
    overlays = edl.get("overlays") or []
    if args.no_loudnorm:
        # Composite directly to final output
        build_final_composite(base_path, overlays, subs_path, out_path, edit_dir, rate=out_rate)
    else:
        # Composite to a temp file, then run loudnorm → final output
        tmp_composite = out_path.with_suffix(".prenorm.mp4")
        build_final_composite(base_path, overlays, subs_path, tmp_composite, edit_dir, rate=out_rate)
        print(f"loudness normalization → social-ready "
              f"({LOUDNORM_I:g} LUFS / {LOUDNORM_TP:g} dBTP / LRA {LOUDNORM_LRA:g})")
        apply_loudnorm_two_pass(tmp_composite, out_path, preview=args.draft)
        tmp_composite.unlink(missing_ok=True)

    # 5. Trilha musical — SEMPRE depois do loudnorm da fala (Regra Dura 14).
    #    Somar música antes da normalização desregula a medição e estoura o pico.
    music = edl.get("music")
    if music:
        music_path = resolve_path(music["file"], edit_dir)
        if not music_path.exists():
            print(f"warning: trilha não encontrada: {music_path} — pulando")
        else:
            helper = Path(__file__).parent / "audio_post.py"
            tmp_music = out_path.with_suffix(".nomusic.mp4")
            out_path.replace(tmp_music)
            cmd = [
                sys.executable, str(helper), str(tmp_music), "-o", str(out_path),
                "--music", str(music_path),
                "--music-db", str(music.get("db", -20)),
            ]
            if music.get("duck", True):
                cmd.append("--duck")
            if music.get("fade_in") is not None:
                cmd += ["--fade-in", str(music["fade_in"])]
            if music.get("fade_out") is not None:
                cmd += ["--fade-out", str(music["fade_out"])]
            print(f"trilha musical → {music_path.name} "
                  f"({music.get('db', -20)}dB, ducking {'on' if music.get('duck', True) else 'off'})")
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                print(proc.stdout[-1500:])
                print(proc.stderr[-1500:], file=sys.stderr)
                out_path.unlink(missing_ok=True)
                tmp_music.replace(out_path)
                print("warning: falha ao mixar a trilha — saída mantida sem música")
            else:
                tmp_music.unlink(missing_ok=True)

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\ndone: {out_path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()

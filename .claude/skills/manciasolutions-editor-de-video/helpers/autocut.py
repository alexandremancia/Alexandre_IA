"""Propõe um corte a partir do transcript: silêncio, filler, gagueira, retake.

É o "auto-cut"/"remover silêncios" do CapCut e do Descript, mas o julgamento
final continua sendo do LLM e do usuário: este helper PROPÕE um edl.json
candidato e um relatório. Nunca aplique sem confirmação (Regra Dura 11).

Uso:
    python helpers/autocut.py --edit-dir edit/ --source C0103 -o edit/edl.json
    python helpers/autocut.py --edit-dir edit/ --all --max-silence 0.35 --keep-fillers
    python helpers/autocut.py --edit-dir edit/ --all --report-only
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# Fillers PT-BR + EN. Removidos só quando isolados entre pausas — "tipo" dentro
# de "tipo de arquivo" é conteúdo, não filler (ver is_isolated_filler).
FILLERS_PT = {
    "né", "ne", "tipo", "assim", "então", "entao", "ahn", "ahm", "hum", "hm",
    "éé", "ééé", "aham", "tá", "ta", "sabe", "cara", "ó", "olha", "putz",
}
FILLERS_EN = {
    "um", "uh", "uhm", "er", "ah", "like", "so", "well", "okay", "ok",
    "right", "actually", "basically", "literally", "you know", "i mean",
}
FILLERS = FILLERS_PT | FILLERS_EN

# Eventos de áudio que o Scribe marca entre parênteses.
AUDIO_EVENT_RE = re.compile(r"^\(.*\)$")
BREATH_EVENTS = {"(breathes)", "(inhales)", "(exhales)", "(sighs)", "(breath)"}
KEEP_EVENTS = {"(laughs)", "(applause)", "(cheers)", "(music)"}


@dataclass
class Segment:
    source: str
    start: float
    end: float
    reason: str = ""
    quote: str = ""

    @property
    def dur(self) -> float:
        return self.end - self.start


def norm(text: str) -> str:
    return re.sub(r"[^\wáàâãéêíóôõúüç]+", "", text.lower(), flags=re.UNICODE)


def load_words(transcript: dict) -> list[dict]:
    return [
        w for w in transcript.get("words", [])
        if w.get("type") in ("word", "audio_event") and w.get("start") is not None and w.get("end") is not None
    ]


def is_isolated_filler(words: list[dict], i: int, gap_before: float, gap_after: float) -> bool:
    """Filler só conta se estiver cercado de pausa — senão é conteúdo."""
    t = norm(words[i].get("text", ""))
    if t not in FILLERS:
        return False
    return gap_before >= 0.18 or gap_after >= 0.18


def detect_false_starts(words: list[dict], window: int = 5) -> set[int]:
    """Marca índices de falsos começos: sequência curta repetida logo em seguida.

    'a gente vai... a gente vai fazer' → a primeira ocorrência sai.
    """
    drop: set[int] = set()
    n = len(words)
    toks = [norm(w.get("text", "")) for w in words]

    i = 0
    while i < n:
        matched = False
        for size in range(window, 1, -1):
            if i + 2 * size > n:
                continue
            a = toks[i:i + size]
            b = toks[i + size:i + 2 * size]
            if all(a) and a == b:
                drop.update(range(i, i + size))
                i += size
                matched = True
                break
        if not matched:
            i += 1
    return drop


def build_keep_ranges(
    words: list[dict],
    max_silence: float,
    pad_in: float,
    pad_out: float,
    drop_fillers: bool,
    drop_false_starts: bool,
    drop_breaths: bool,
) -> tuple[list[tuple[float, float, list[str]]], dict]:
    """Retorna faixas a MANTER + estatísticas do que foi removido."""
    stats = {"silence_s": 0.0, "fillers": 0, "false_starts": 0, "breaths": 0, "words_total": len(words)}

    false_start_idx = detect_false_starts(words) if drop_false_starts else set()

    keep_flags: list[bool] = []
    for i, w in enumerate(words):
        text = w.get("text", "").strip()
        gap_before = w["start"] - words[i - 1]["end"] if i > 0 else 0.0
        gap_after = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 0.0

        keep = True
        if AUDIO_EVENT_RE.match(text):
            low = text.lower()
            if drop_breaths and low in BREATH_EVENTS:
                keep = False
                stats["breaths"] += 1
            elif low not in KEEP_EVENTS:
                keep = False
        elif i in false_start_idx:
            keep = False
            stats["false_starts"] += 1
        elif drop_fillers and is_isolated_filler(words, i, gap_before, gap_after):
            keep = False
            stats["fillers"] += 1
        keep_flags.append(keep)

    # Agrupa palavras mantidas em faixas contínuas, quebrando em silêncio longo.
    ranges: list[tuple[float, float, list[str]]] = []
    cur_start: float | None = None
    cur_end: float = 0.0
    cur_words: list[str] = []

    for i, w in enumerate(words):
        if not keep_flags[i]:
            continue
        if cur_start is None:
            cur_start, cur_end, cur_words = w["start"], w["end"], [w.get("text", "").strip()]
            continue
        gap = w["start"] - cur_end
        if gap > max_silence:
            stats["silence_s"] += gap - max_silence
            ranges.append((cur_start, cur_end, cur_words))
            cur_start, cur_end, cur_words = w["start"], w["end"], [w.get("text", "").strip()]
        else:
            cur_end = w["end"]
            cur_words.append(w.get("text", "").strip())

    if cur_start is not None:
        ranges.append((cur_start, cur_end, cur_words))

    # Padding nas bordas (Regra Dura 7: janela 30-200ms).
    padded = []
    for idx, (s, e, ws) in enumerate(ranges):
        ps = max(0.0, s - pad_in)
        pe = e + pad_out
        if idx > 0:
            prev_end = padded[-1][1]
            if ps < prev_end:
                ps = prev_end
        padded.append((ps, pe, ws))

    return padded, stats


def probe_duration(path: Path) -> float:
    """Duração real da fonte, ou 0.0 se não der para ler."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


def clamp_to_source(ranges, duration: float, stem: str):
    """Prende as faixas ao fim do arquivo. Devolve (faixas, segundos podados).

    Transcript pode reivindicar tempo que não existe: ASR alucina além do fim
    do áudio, e um transcript em cache envelhece se a fonte for recortada
    depois. O EDL então pede material inexistente, o ffmpeg entrega o que tem,
    e o render sai mais curto que o planejado — sem erro nenhum, só um QC
    reclamando de duração lá na frente.
    """
    if duration <= 0:
        return ranges, 0.0
    saida, podado = [], 0.0
    for start, end, ws in ranges:
        if start >= duration:
            podado += end - start
            continue
        if end > duration:
            podado += end - duration
            end = duration
        if end - start > 0:
            saida.append((start, end, ws))
    return saida, podado


def merge_adjacent(ranges: list[tuple[float, float, list[str]]], min_gap: float = 0.12):
    """Junta faixas separadas por menos que min_gap — corte imperceptível não vale um corte."""
    if not ranges:
        return ranges
    out = [list(ranges[0])]
    for s, e, ws in ranges[1:]:
        if s - out[-1][1] < min_gap:
            out[-1][1] = e
            out[-1][2] = out[-1][2] + ws
        else:
            out.append([s, e, ws])
    return [tuple(r) for r in out]


def process_source(
    stem: str,
    transcript: dict,
    source_path: str,
    args,
) -> tuple[list[Segment], dict]:
    words = load_words(transcript)
    if not words:
        return [], {"words_total": 0}

    ranges, stats = build_keep_ranges(
        words,
        max_silence=args.max_silence,
        pad_in=args.pad_in,
        pad_out=args.pad_out,
        drop_fillers=not args.keep_fillers,
        drop_false_starts=not args.keep_false_starts,
        drop_breaths=not args.keep_breaths,
    )
    ranges = merge_adjacent(ranges, args.min_gap)

    dur = probe_duration(Path(source_path))
    ranges, podado = clamp_to_source(ranges, dur, stem)
    if podado > 0.01:
        print(f"  aviso: {stem} — o transcript reivindica {podado:.2f}s além do fim do "
              f"arquivo ({dur:.2f}s). Faixas presas ao fim.", file=sys.stderr)
        print(f"         Se a fonte foi recortada depois de transcrita, apague "
              f"transcripts/{stem}.json e transcreva de novo.", file=sys.stderr)

    ranges = [r for r in ranges if (r[1] - r[0]) >= args.min_segment]

    segs = [
        Segment(
            source=stem,
            start=round(s, 3),
            end=round(e, 3),
            quote=" ".join(ws)[:180],
            reason="autocut: fala contínua",
        )
        for s, e, ws in ranges
    ]
    return segs, stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Propõe cortes automáticos a partir do transcript")
    ap.add_argument("--edit-dir", type=Path, required=True, help="Diretório edit/")
    ap.add_argument("--source", action="append", default=[], help="Stem do source (repetível)")
    ap.add_argument("--all", action="store_true", help="Todos os transcripts do diretório")
    ap.add_argument("-o", "--output", type=Path, default=None, help="edl.json de saída")
    ap.add_argument("--max-silence", type=float, default=0.45, help="Silêncio tolerado dentro de um segmento (s)")
    ap.add_argument("--pad-in", type=float, default=0.05, help="Padding antes da primeira palavra (s)")
    ap.add_argument("--pad-out", type=float, default=0.08, help="Padding depois da última palavra (s)")
    ap.add_argument("--min-gap", type=float, default=0.12, help="Abaixo disso, junta os segmentos")
    ap.add_argument("--min-segment", type=float, default=0.35, help="Descarta segmentos mais curtos que isso")
    ap.add_argument("--keep-fillers", action="store_true", help="Não remove né/tipo/uh")
    ap.add_argument("--keep-false-starts", action="store_true", help="Não remove repetições de início")
    ap.add_argument("--keep-breaths", action="store_true", help="Não remove (breathes)/(sighs)")
    ap.add_argument("--grade", default="none", help="Preset de grade para o EDL")
    ap.add_argument("--report-only", action="store_true", help="Só imprime o relatório, não escreve EDL")
    args = ap.parse_args()

    tdir = args.edit_dir / "transcripts"
    if not tdir.exists():
        print(f"erro: {tdir} não existe — rode transcribe_batch.py antes", file=sys.stderr)
        sys.exit(1)

    if args.all:
        tfiles = sorted(tdir.glob("*.json"))
    else:
        tfiles = [tdir / f"{s}.json" for s in args.source]
    if not tfiles:
        print("erro: nenhum transcript selecionado (use --all ou --source)", file=sys.stderr)
        sys.exit(1)

    sources: dict[str, str] = {}
    all_segs: list[Segment] = []
    total_stats = {"silence_s": 0.0, "fillers": 0, "false_starts": 0, "breaths": 0, "words_total": 0}
    original_total = 0.0

    for tf in tfiles:
        if not tf.exists():
            print(f"aviso: {tf} não encontrado, pulando", file=sys.stderr)
            continue
        transcript = json.loads(tf.read_text())
        stem = tf.stem
        src_path = transcript.get("source_path") or str(args.edit_dir.parent / f"{stem}.mp4")
        sources[stem] = src_path

        words = load_words(transcript)
        if words:
            original_total += words[-1]["end"] - words[0]["start"]

        segs, stats = process_source(stem, transcript, src_path, args)
        all_segs.extend(segs)
        for k in total_stats:
            total_stats[k] += stats.get(k, 0)

    cut_total = sum(s.dur for s in all_segs)

    print(f"\n── autocut ─────────────────────────────")
    print(f"fontes            {len(tfiles)}")
    print(f"palavras          {total_stats['words_total']}")
    print(f"segmentos         {len(all_segs)}")
    print(f"fillers removidos {total_stats['fillers']}")
    print(f"falsos começos    {total_stats['false_starts']}")
    print(f"respirações       {total_stats['breaths']}")
    print(f"silêncio cortado  {total_stats['silence_s']:.1f}s")
    print(f"duração original  {original_total:.1f}s")
    print(f"duração proposta  {cut_total:.1f}s", end="")
    if original_total > 0:
        print(f"  ({100 * (1 - cut_total / original_total):.0f}% mais curto)")
    else:
        print()
    print("────────────────────────────────────────")
    print("Isto é uma PROPOSTA. Confirme com o usuário antes de renderizar.\n")

    if args.report_only:
        return

    edl = {
        "version": 1,
        "sources": {k: str(Path(v).resolve()) for k, v in sources.items()},
        "ranges": [asdict(s) for s in all_segs],
        "grade": args.grade,
        "overlays": [],
        "total_duration_s": round(cut_total, 2),
    }
    out = args.output or (args.edit_dir / "edl_autocut.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(edl, indent=2, ensure_ascii=False))
    print(f"✓ {out}")


if __name__ == "__main__":
    main()

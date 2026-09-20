"""Gera legendas ASS animadas (karaokê, pop, hormozi, doc, clean).

O CapCut chama isso de "legendas automáticas com destaque". Aqui é ASS puro,
gerado a partir do transcript word-level — nunca de um SRT reinterpolado
(Regra Dura 16). Todo tempo é calculado na timeline de SAÍDA:

    t_saida = palavra.start - segmento.start + offset_do_segmento

que é a mesma matemática do build_master_srt() do render.py (Regra Dura 5).

Uso:
    python helpers/captions.py <edl.json> --edit-dir <dir> -o master.ass --style karaoke
    python helpers/captions.py <edl.json> --edit-dir <dir> -o master.ass --style hormozi --accent "#FFD400"
    python helpers/captions.py --from-transcript transcripts/C0103.json -o legenda.ass --style doc

Depois passe o .ass no campo "subtitles" do edl.json. O render.py aplica por
último na cadeia de filtros (Regra Dura 1).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Cor
# ---------------------------------------------------------------------------


def hex_to_ass(color: str, alpha: int = 0) -> str:
    """'#RRGGBB' -> '&HAABBGGRR' (ASS inverte a ordem dos canais)."""
    c = color.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        raise ValueError(f"cor inválida: {color!r} (esperado #RRGGBB)")
    r, g, b = c[0:2], c[2:4], c[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def ass_time(seconds: float) -> str:
    """ASS usa H:MM:SS.cc (centésimos, não milésimos)."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    h, rem = divmod(total_cs, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------


@dataclass
class CaptionStyle:
    name: str
    font: str = "Helvetica"
    # Tamanho, contorno e margens são FRAÇÕES DA ALTURA do quadro, não pixels.
    # Com PlayRes igual à resolução real, FontSize passa a ser pixel de verdade,
    # e a mesma legenda fica proporcional em 1080p, 4K e 9:16 sem recalibrar.
    size_pct: float = 0.055     # 59px em 1080p
    bold: int = 1
    outline_pct: float = 0.0035
    shadow: float = 0.0
    margin_v_pct: float = 0.06  # sobrescrito por aspecto (ver margin_for_aspect)
    margin_h_pct: float = 0.06
    alignment: int = 2          # 2 = centro-baixo
    max_words: int = 2
    uppercase: bool = True
    highlight: bool = True      # pinta a palavra corrente com a cor de destaque
    pop: bool = False           # anima escala na entrada da palavra
    karaoke: bool = False       # usa tag \k (varredura contínua)
    break_on_punct: bool = True
    base_color: str = "#FFFFFF"
    accent_color: str = "#FF5A00"
    outline_color: str = "#000000"
    box: bool = False           # BorderStyle=3 (caixa opaca atrás do texto)
    max_line_chars: int = 22    # acima disso, quebra em duas linhas
    description: str = ""


# A margem inferior NÃO é gosto, é safe-zone — e ela depende do aspecto.
#
# Em 9:16 a UI de TikTok/Reels/Shorts cobre ~25-30% da base do quadro: legenda
# encostada embaixo fica atrás de @usuário, descrição e música. Daí ~18% de
# margem. Em 16:9 não existe UI nenhuma ali, e a mesma margem joga a legenda
# para o meio da tela, onde ela atrapalha a imagem em vez de acompanhá-la.
MARGIN_V_BY_ASPECT = {
    "9:16": 0.18,
    "4:5": 0.12,
    "1:1": 0.10,
    "16:9": 0.07,
    "4:3": 0.07,
}


def margin_for_aspect(width: int, height: int) -> float:
    """Fração da altura a reservar embaixo, escolhida pelo aspecto real."""
    ratio = width / height if height else 1.0
    if ratio < 0.7:       # 9:16 e mais estreito
        return MARGIN_V_BY_ASPECT["9:16"]
    if ratio < 0.9:       # 4:5
        return MARGIN_V_BY_ASPECT["4:5"]
    if ratio < 1.2:       # 1:1
        return MARGIN_V_BY_ASPECT["1:1"]
    return MARGIN_V_BY_ASPECT["16:9"]


STYLES: dict[str, CaptionStyle] = {
    "karaoke": CaptionStyle(
        name="karaoke",
        max_words=4,
        uppercase=True,
        karaoke=True,
        highlight=False,
        size_pct=0.052,
        outline_pct=0.004,
        max_line_chars=24,
        description="Varredura contínua: a palavra acende conforme é falada. Música, lyric video, alta energia.",
    ),
    "pop": CaptionStyle(
        name="pop",
        max_words=1,
        uppercase=True,
        pop=True,
        highlight=False,
        size_pct=0.085,
        outline_pct=0.006,
        max_line_chars=14,
        description="Uma palavra por vez, entrando com escala. Máxima retenção em vertical curto.",
    ),
    "hormozi": CaptionStyle(
        name="hormozi",
        max_words=3,
        uppercase=True,
        highlight=True,
        size_pct=0.062,
        outline_pct=0.006,
        accent_color="#FFD400",
        max_line_chars=18,
        description="Bloco curto em caixa alta, palavra corrente em amarelo. Padrão de short viral.",
    ),
    "doc": CaptionStyle(
        name="doc",
        max_words=7,
        uppercase=False,
        highlight=False,
        bold=0,
        size_pct=0.040,
        outline_pct=0.0025,
        max_line_chars=40,
        description="Frase natural, sóbria. Documentário, entrevista, institucional, aula.",
    ),
    "clean": CaptionStyle(
        name="clean",
        max_words=4,
        uppercase=False,
        highlight=False,
        size_pct=0.045,
        outline_pct=0.0035,
        max_line_chars=30,
        description="Meio-termo legível. Tutorial, vlog, conteúdo longo em horizontal.",
    ),
    "box": CaptionStyle(
        name="box",
        max_words=5,
        uppercase=False,
        highlight=False,
        size_pct=0.042,
        outline_pct=0.002,
        box=True,
        max_line_chars=34,
        description="Caixa opaca atrás do texto. Fundo claro ou muito texturizado, onde contorno não basta.",
    ),
}


# ---------------------------------------------------------------------------
# Leitura do transcript / EDL
# ---------------------------------------------------------------------------


@dataclass
class Word:
    text: str
    start: float   # já na timeline de saída
    end: float
    speaker: str | None = None


@dataclass
class Chunk:
    words: list[Word] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end


def _is_word(w: dict) -> bool:
    return w.get("type") == "word" and w.get("start") is not None and w.get("end") is not None


def words_from_transcript(transcript: dict, t_start: float, t_end: float) -> list[dict]:
    out = []
    for w in transcript.get("words", []):
        if not _is_word(w):
            continue
        if w["end"] <= t_start or w["start"] >= t_end:
            continue
        out.append(w)
    return out


def collect_words_from_edl(edl: dict, edit_dir: Path) -> list[Word]:
    """Palavras de todos os segmentos, remapeadas para a timeline de saída."""
    transcripts_dir = edit_dir / "transcripts"
    sources = edl["sources"]
    cache: dict[str, dict] = {}
    words: list[Word] = []
    offset = 0.0

    for seg in edl["ranges"]:
        src_key = seg["source"]
        seg_start = float(seg["start"])
        seg_end = float(seg["end"])
        seg_dur = seg_end - seg_start
        speed = float(seg.get("speed", 1.0)) or 1.0

        stem = Path(sources[src_key]).stem
        if stem not in cache:
            tpath = transcripts_dir / f"{stem}.json"
            if not tpath.exists():
                print(f"  aviso: sem transcript para {stem}, segmento sem legenda", file=sys.stderr)
                cache[stem] = {"words": []}
            else:
                cache[stem] = json.loads(tpath.read_text())
        transcript = cache[stem]

        for w in words_from_transcript(transcript, seg_start, seg_end):
            ws = max(w["start"], seg_start) - seg_start
            we = min(w["end"], seg_end) - seg_start
            # speed ramp comprime/estica o tempo do segmento
            words.append(
                Word(
                    text=w["text"].strip(),
                    start=offset + ws / speed,
                    end=offset + we / speed,
                    speaker=w.get("speaker_id"),
                )
            )
        offset += seg_dur / speed

    return words


def collect_words_from_transcript(transcript: dict) -> list[Word]:
    return [
        Word(text=w["text"].strip(), start=w["start"], end=w["end"], speaker=w.get("speaker_id"))
        for w in transcript.get("words", [])
        if _is_word(w)
    ]


# ---------------------------------------------------------------------------
# Agrupamento em chunks
# ---------------------------------------------------------------------------

PUNCT_END = ".!?…"
PUNCT_SOFT = ",;:—-"


def chunk_words(
    words: list[Word],
    max_words: int,
    break_on_punct: bool = True,
    max_gap: float = 0.6,
    break_on_speaker: bool = True,
) -> list[Chunk]:
    """Quebra em blocos por contagem, pontuação, silêncio e troca de falante."""
    chunks: list[Chunk] = []
    cur = Chunk()

    for i, w in enumerate(words):
        if not w.text:
            continue
        if cur.words:
            prev = cur.words[-1]
            gap = w.start - prev.end
            hard_break = (
                len(cur.words) >= max_words
                or gap >= max_gap
                or (break_on_speaker and w.speaker != prev.speaker)
                or (break_on_punct and prev.text and prev.text[-1] in PUNCT_END)
            )
            if hard_break:
                chunks.append(cur)
                cur = Chunk()
        cur.words.append(w)

    if cur.words:
        chunks.append(cur)
    return chunks


def hold_chunks(chunks: list[Chunk], min_dur: float = 0.5, max_hold: float = 0.35) -> list[tuple[Chunk, float, float]]:
    """Calcula (chunk, t_in, t_out) estendendo blocos curtos sem invadir o próximo.

    Bloco com duração natural abaixo de min_dur pisca. Estende até o próximo
    bloco ou até max_hold além do fim da fala, o que vier primeiro.
    """
    out = []
    for i, ch in enumerate(chunks):
        t_in = ch.start
        t_out = ch.end
        nxt = chunks[i + 1].start if i + 1 < len(chunks) else None
        want = max(t_out, t_in + min_dur, t_out + max_hold)
        if nxt is not None:
            t_out = min(want, nxt)
        else:
            t_out = want
        if t_out <= t_in:
            t_out = t_in + 0.2
        out.append((ch, t_in, t_out))
    return out


# ---------------------------------------------------------------------------
# Geração ASS
# ---------------------------------------------------------------------------


def ass_header(style: CaptionStyle, play_x: int, play_y: int,
               margin_v_pct: float | None = None) -> str:
    """Cabeçalho ASS com PlayRes igual à resolução REAL da saída.

    Com PlayRes casando com o vídeo, FontSize e margens viram pixels de
    verdade, e um percentual da altura rende o mesmo enquadramento em 1080p,
    4K e 9:16. Com um PlayRes fixo (384x288, como faz muita gente), o libass
    reescala por um fator que depende do vídeo e o mesmo número de fonte sai
    de tamanhos diferentes conforme a entrega.

    WrapStyle 0 (e não 2): o 2 DESLIGA a quebra automática, então um bloco
    comprido atravessa o quadro e sai pelas bordas em vez de virar duas linhas.
    """
    border_style = 3 if style.box else 1
    back = hex_to_ass(style.outline_color)
    primary = hex_to_ass(style.accent_color if style.karaoke else style.base_color)
    secondary = hex_to_ass(style.base_color if style.karaoke else style.accent_color)

    size = max(8, round(style.size_pct * play_y))
    outline = max(1.0, round(style.outline_pct * play_y, 1))
    margin_v = round((margin_v_pct if margin_v_pct is not None else style.margin_v_pct) * play_y)
    margin_h = round(style.margin_h_pct * play_x)

    return f"""[Script Info]
; Gerado por manciasolutions-editor-de-video / captions.py — estilo: {style.name}
; Resolução de referência: {play_x}x{play_y} (case com a saída, senão a fonte muda de tamanho)
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {play_x}
PlayResY: {play_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font},{size},{primary},{secondary},{hex_to_ass(style.outline_color)},{back},{style.bold},0,0,0,100,100,0,0,{border_style},{outline},{style.shadow},{style.alignment},{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _txt(word: Word, style: CaptionStyle) -> str:
    t = word.text
    return t.upper() if style.uppercase else t


def _dialogue(t_in: float, t_out: float, text: str, layer: int = 0) -> str:
    return f"Dialogue: {layer},{ass_time(t_in)},{ass_time(t_out)},Default,,0,0,0,,{text}\n"


def balance_lines(words_text: list[str], max_chars: int) -> list[list[int]]:
    """Agrupa índices de palavras em linhas de no máximo `max_chars`.

    O WrapStyle 0 já quebra sozinho, mas quebra onde couber — o que costuma
    deixar uma linha cheia e outra com uma palavra solta. Dividir no meio do
    texto dá duas linhas parecidas, que é o que se lê melhor.
    """
    total = sum(len(w) for w in words_text) + len(words_text) - 1
    if total <= max_chars or len(words_text) < 2:
        return [list(range(len(words_text)))]

    alvo = total / 2
    melhor_corte, melhor_erro = 1, float("inf")
    acumulado = 0
    for i in range(len(words_text) - 1):
        acumulado += len(words_text[i]) + 1
        erro = abs(acumulado - alvo)
        if erro < melhor_erro:
            melhor_erro, melhor_corte = erro, i + 1
    return [list(range(melhor_corte)), list(range(melhor_corte, len(words_text)))]


def join_with_breaks(pieces: list[str], plain: list[str], max_chars: int) -> str:
    """Junta os trechos já formatados, inserindo \\N nas quebras de linha."""
    linhas = balance_lines(plain, max_chars)
    return r"\N".join(" ".join(pieces[i] for i in linha) for linha in linhas)


def render_events(chunks: list[tuple[Chunk, float, float]], style: CaptionStyle) -> str:
    out = []
    accent = hex_to_ass(style.accent_color)
    base = hex_to_ass(style.base_color)

    for ch, t_in, t_out in chunks:
        words = ch.words

        if style.karaoke:
            # Uma linha só; \k em centésimos varre da SecondaryColour p/ PrimaryColour.
            parts = []
            cursor = t_in
            for w in words:
                lead = max(0, int(round((w.start - cursor) * 100)))
                dur = max(1, int(round((w.end - w.start) * 100)))
                if lead:
                    parts.append(r"{\k%d}" % lead)
                parts.append(r"{\kf%d}%s " % (dur, _txt(w, style)))
                cursor = w.end
            out.append(_dialogue(t_in, t_out, "".join(parts).rstrip()))
            continue

        if style.pop:
            # Uma palavra por evento, entrando com escala (ease-out via \t).
            for i, w in enumerate(words):
                w_in = w.start
                w_out = words[i + 1].start if i + 1 < len(words) else t_out
                if w_out <= w_in:
                    w_out = w_in + 0.15
                tag = r"{\fscx70\fscy70\t(0,90,\fscx100\fscy100)}"
                out.append(_dialogue(w_in, w_out, tag + _txt(w, style)))
            continue

        if style.highlight and len(words) > 1:
            # Bloco inteiro visível, palavra corrente em destaque (estilo CapCut).
            for i, w in enumerate(words):
                w_in = w.start if i > 0 else t_in
                w_out = words[i + 1].start if i + 1 < len(words) else t_out
                if w_out <= w_in:
                    w_out = w_in + 0.1
                pieces = []
                for j, ww in enumerate(words):
                    color = accent if j == i else base
                    pieces.append(r"{\c%s}%s" % (color, _txt(ww, style)))
                plain = [_txt(ww, style) for ww in words]
                out.append(_dialogue(w_in, w_out,
                                     join_with_breaks(pieces, plain, style.max_line_chars)))
            continue

        # Estático: bloco inteiro, sem destaque.
        plain = [_txt(w, style) for w in words]
        out.append(_dialogue(t_in, t_out,
                             join_with_breaks(plain, plain, style.max_line_chars)))

    return "".join(out)


def build_ass(
    words: list[Word],
    style: CaptionStyle,
    play_x: int = 1920,
    play_y: int = 1080,
    margin_v_pct: float | None = None,
) -> str:
    chunks = chunk_words(words, style.max_words, style.break_on_punct)
    timed = hold_chunks(chunks)
    if margin_v_pct is None:
        margin_v_pct = margin_for_aspect(play_x, play_y)
    return (ass_header(style, play_x, play_y, margin_v_pct)
            + render_events(timed, style))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def resolve_resolution(args) -> tuple[int, int]:
    """Resolução de referência: --res, senão sondada de --video, senão 1920x1080."""
    if args.res:
        try:
            w, h = args.res.lower().replace("×", "x").split("x")
            return int(w), int(h)
        except ValueError:
            raise SystemExit(f"--res inválido: {args.res!r} (esperado LARGURAxALTURA)")
    if args.video:
        import subprocess
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(args.video)],
            capture_output=True, text=True,
        )
        try:
            w, h = proc.stdout.strip().split("x")
            return int(w), int(h)
        except ValueError:
            print(f"aviso: não consegui ler a resolução de {args.video}; usando 1920x1080",
                  file=sys.stderr)
    return 1920, 1080


def main() -> None:
    ap = argparse.ArgumentParser(description="Gera legendas ASS animadas a partir de transcript word-level")
    ap.add_argument("edl", type=Path, nargs="?", help="edl.json (timeline de saída)")
    ap.add_argument("--from-transcript", type=Path, default=None, help="Legenda um transcript único, sem EDL")
    ap.add_argument("--edit-dir", type=Path, default=None, help="Diretório edit/ (padrão: pasta do edl.json)")
    ap.add_argument("-o", "--output", type=Path, required=False, help="Arquivo .ass de saída")
    ap.add_argument("--style", default="hormozi", choices=sorted(STYLES), help="Estilo de legenda")
    ap.add_argument("--accent", default=None, help="Cor de destaque (#RRGGBB)")
    ap.add_argument("--base", default=None, help="Cor base do texto (#RRGGBB)")
    ap.add_argument("--font", default=None, help="Nome da fonte")
    ap.add_argument("--size", type=float, default=None,
                    help="Altura da fonte como fração da altura do quadro (ex. 0.06 = 6%%)")
    ap.add_argument("--max-words", type=int, default=None, help="Palavras por bloco")
    ap.add_argument("--margin-v", type=float, default=None,
                    help="Margem inferior como fração da altura (ex. 0.18 em 9:16)")
    ap.add_argument("--res", default=None,
                    help="Resolução da saída, ex. 1080x1920. Padrão: lida do vídeo com --video, "
                         "senão 1920x1080")
    ap.add_argument("--video", type=Path, default=None,
                    help="Vídeo de saída, só para ler a resolução (não é modificado)")
    ap.add_argument("--uppercase", dest="uppercase", action="store_true", default=None)
    ap.add_argument("--no-uppercase", dest="uppercase", action="store_false")
    ap.add_argument("--no-write-edl", action="store_true",
                    help="Não grava o campo 'subtitles' de volta no edl.json")
    ap.add_argument("--list-styles", action="store_true", help="Lista os estilos e sai")
    args = ap.parse_args()

    if args.list_styles:
        for name, st in STYLES.items():
            print(f"{name:10s} {st.max_words} palavra(s)/bloco  {st.description}")
        return

    style = STYLES[args.style]
    # cópia para não mutar o catálogo global
    style = CaptionStyle(**{**style.__dict__})
    for attr, val in (
        ("accent_color", args.accent),
        ("base_color", args.base),
        ("font", args.font),
        ("size_pct", args.size),
        ("max_words", args.max_words),
        ("uppercase", args.uppercase),
    ):
        if val is not None:
            setattr(style, attr, val)

    if args.from_transcript:
        transcript = json.loads(args.from_transcript.read_text())
        words = collect_words_from_transcript(transcript)
    else:
        if not args.edl:
            ap.error("passe um edl.json ou --from-transcript")
        edl = json.loads(args.edl.read_text())
        edit_dir = args.edit_dir or args.edl.parent
        words = collect_words_from_edl(edl, edit_dir)

    if not words:
        print("nenhuma palavra encontrada — legenda vazia não será escrita", file=sys.stderr)
        sys.exit(1)

    play_x, play_y = resolve_resolution(args)
    ass = build_ass(words, style, play_x, play_y, margin_v_pct=args.margin_v)

    out = args.output or Path("master.ass")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ass)

    n_events = ass.count("Dialogue:")
    margin_pct = args.margin_v if args.margin_v is not None else margin_for_aspect(play_x, play_y)
    print(f"✓ {out}  ({n_events} eventos, estilo {style.name}, {len(words)} palavras)")
    print(f"  referência {play_x}x{play_y}, fonte {round(style.size_pct * play_y)}px, "
          f"margem inferior {round(margin_pct * play_y)}px")
    print(f"  A legenda TEM de ser aplicada nesta resolução — em outra, a fonte sai "
          f"de tamanho errado.")

    # Gerar o .ass não faz o render usá-lo: o campo `subtitles` do EDL é que
    # manda. Sem este passo é fácil renderizar sem legenda e só notar no QC.
    if args.edl and not args.no_write_edl:
        edl_data = json.loads(args.edl.read_text())
        try:
            rel = out.resolve().relative_to(args.edl.resolve().parent)
            valor = str(rel)
        except ValueError:
            valor = str(out.resolve())
        anterior = edl_data.get("subtitles")
        if anterior == valor:
            print(f"  EDL já aponta para esta legenda")
        else:
            edl_data["subtitles"] = valor
            args.edl.write_text(json.dumps(edl_data, indent=2, ensure_ascii=False))
            if anterior:
                print(f"  {args.edl.name}: subtitles {anterior!r} → {valor!r}")
            else:
                print(f"  {args.edl.name}: subtitles = {valor!r}")
        print(f"  Renderize com:  render.py {args.edl} -o saida.mp4 --size {play_x}x{play_y}")


if __name__ == "__main__":
    main()

"""Caption style library — pick a preset instead of hand-tuning ASS force_style
every time. render.py's --caption-style flag looks names up here.

## The MarginV trap (read this before adding a preset)

libass does NOT interpret MarginV in output pixels. It scales the whole
subtitle render against a virtual canvas whose height is PlayResY, which
defaults to 288 when the force_style string doesn't set one. So:

    fracao da altura do quadro a partir da base = MarginV / 288

A MarginV=140 therefore sits at 140/288 ~= 49% of frame height — almost dead
center, not "a bit above the bottom". This is the single easiest way to ship
a caption that looks fine in the ffmpeg log and wrong on screen, and it is
invisible to any check that isn't a rendered frame.

Same for FontSize: it is also relative to PlayResY=288, so FontSize=18 is
roughly 6% of frame height regardless of whether the output is 1080p or 4K.
That scale-independence is the reason these presets work on any resolution.

## Why margins are per-format

The safe zone differs by delivery format, so one MarginV cannot serve both:

  - Vertical (Reels / TikTok / Shorts): the platform UI — caption text,
    username, audio attribution, right-rail action buttons — covers roughly
    the bottom 25-30% of the frame. Captions must clear it, so MarginV lands
    around 90 (~31%).
  - Horizontal (YouTube / presentations): almost nothing overlays the bottom
    edge except a transient player scrubber, so captions sit low, around
    MarginV 28-34 (~10-12%).

Each preset therefore declares BOTH, and `force_style_for()` picks the right
one from the --format target. Getting this wrong doesn't error — it just
renders the caption in the wrong place, which is exactly why it's documented
here rather than left to taste.
"""

from __future__ import annotations

# libass's default virtual canvas height. Every MarginV/FontSize below is
# expressed against this, NOT in output pixels.
PLAY_RES_Y = 288

# Which format targets count as vertical for safe-zone purposes.
VERTICAL_TARGETS = {"vertical-reel", "vertical-story"}


PRESETS: dict[str, dict] = {
    # video-use's original default: readable, understated, works for any content.
    "natural-sentence": {
        "max_words": 10,
        "uppercase": False,
        "margin_v_vertical": 90,
        "margin_v_horizontal": 30,
        "base_style": (
            "FontName=Arial,FontSize=13,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=1,Outline=1.6,Shadow=0.6,"
            "Alignment=2"
        ),
        "description": "Frase completa, legivel, discreta. Padrao seguro para qualquer conteudo — "
                        "tutoriais, palestras, videos institucionais.",
    },
    # Big, punchy, word-grouped captions for short-form — the look popularized
    # by Alex Hormozi's editors, now standard on Reels/TikTok/Shorts.
    "bold-overlay": {
        "max_words": 3,
        "uppercase": True,
        "margin_v_vertical": 90,
        "margin_v_horizontal": 34,
        "base_style": (
            "FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,BorderStyle=1,Outline=2.5,Shadow=0,"
            "Bold=1,Alignment=2"
        ),
        "description": "Legenda grande, poucas palavras por vez, alto contraste. Padrao do formato "
                        "short-form de alta retencao (Reels/TikTok/Shorts).",
    },
    # For content where the visual is the point and captions are purely an
    # accessibility / sound-off affordance.
    "minimal-clean": {
        "max_words": 8,
        "uppercase": False,
        "margin_v_vertical": 85,
        "margin_v_horizontal": 28,
        "base_style": (
            "FontName=Arial,FontSize=11,PrimaryColour=&H00E6E6E6,"
            "OutlineColour=&H00000000,BorderStyle=3,BackColour=&H80000000,"
            "Outline=0,Shadow=0,Alignment=2"
        ),
        "description": "Discreta, caixa semitransparente em vez de contorno grosso. Para conteudo "
                        "visual denso onde a legenda nao pode competir por atencao.",
    },
    # Amber primary instead of white — reads as the "highlighted word" look
    # without needing per-word \k timing tags. True per-word karaoke needs an
    # .ass file with \k durations, which build_master_srt does not emit; this
    # preset is the SRT-compatible approximation of that style.
    "karaoke-word": {
        "max_words": 2,
        "uppercase": True,
        "margin_v_vertical": 90,
        "margin_v_horizontal": 34,
        "base_style": (
            "FontName=Arial,FontSize=18,PrimaryColour=&H0000D7FF,"
            "OutlineColour=&H00000000,BorderStyle=1,"
            "Outline=2.5,Shadow=0,Bold=1,Alignment=2"
        ),
        "description": "Chunks curtissimos em ambar — aproxima o efeito 'karaoke' usando SRT comum. "
                        "Karaoke real palavra a palavra exige tags \\k em .ass, que build_master_srt "
                        "ainda nao gera; este preset e a aproximacao compativel.",
    },
}

DEFAULT_PRESET = "natural-sentence"


def get_preset(name: str) -> dict:
    if name not in PRESETS:
        available = ", ".join(sorted(PRESETS))
        raise ValueError(f"unknown caption style '{name}' — available: {available}")
    return PRESETS[name]


def force_style_for(name: str, format_target: str | None = None) -> str:
    """Build the libass force_style string for this preset, with the MarginV
    that matches the delivery format.

    `format_target` is a key from format_targets.TARGETS, or None. None and
    any non-vertical target get the horizontal (low) margin; vertical targets
    get the high margin that clears platform UI. When no --format is passed,
    horizontal is the safer default: a caption too low on a vertical video is
    hidden by UI, but a caption too high on a horizontal video just looks odd
    — and most sources are horizontal to begin with.
    """
    cfg = get_preset(name)
    is_vertical = format_target in VERTICAL_TARGETS
    margin = cfg["margin_v_vertical"] if is_vertical else cfg["margin_v_horizontal"]
    return f"{cfg['base_style']},MarginV={margin}"


def list_presets() -> str:
    lines = [f"estilos de legenda disponiveis (MarginV relativo a PlayResY={PLAY_RES_Y}):", ""]
    for name, cfg in PRESETS.items():
        pv = cfg["margin_v_vertical"] / PLAY_RES_Y * 100
        ph = cfg["margin_v_horizontal"] / PLAY_RES_Y * 100
        lines.append(f"  {name}  (max {cfg['max_words']} palavras/tela, "
                     f"{'MAIUSCULA' if cfg['uppercase'] else 'caixa natural'})")
        lines.append(f"    rodape: {pv:.0f}% da altura no vertical, {ph:.0f}% no horizontal")
        lines.append(f"    {cfg['description']}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(list_presets())

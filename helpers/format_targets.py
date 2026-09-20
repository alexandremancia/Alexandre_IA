"""Output format targets — vertical short-form vs. horizontal long-form.

video-use's ancestor only ever thought in terms of the source aspect ratio.
edvid's whole premise is that the same raw footage should be able to become
either a 9:16 Reel or a 16:9 YouTube video from one edit — this module is
what makes that a --format flag instead of a manual crop job.

Two strategies per non-matching aspect ratio:
  "crop"       — center-crop to the target ratio. Simple, always sharp, but
                 loses the sides of the frame. Fine for a talking head
                 already centered.
  "blur-pad"   — scale the source to fit width/height, and fill the letterbox
                 bars with a blurred, zoomed copy of the same frame instead of
                 flat black. This is the technique virtually every modern
                 Reels/TikTok repost of a horizontal video uses; looks far
                 less "obviously repurposed" than a hard crop or plain bars.

Usage as a library (render.py calls this when an EDL specifies "format"):
    from format_targets import build_reframe_filter
    filter_str = build_reframe_filter("vertical-reel", strategy="blur-pad")

Usage standalone, to preview crop math before committing:
    python helpers/format_targets.py --source 1920x1080 --format vertical-reel
"""

from __future__ import annotations

import argparse

TARGETS: dict[str, dict] = {
    "vertical-reel": {
        "width": 1080,
        "height": 1920,
        "label": "9:16 — Reels / TikTok / Shorts",
    },
    "vertical-story": {
        "width": 1080,
        "height": 1920,
        "label": "9:16 — Stories (mesma proporção do reel, presets de duração diferem no roteiro)",
    },
    "horizontal-youtube": {
        "width": 1920,
        "height": 1080,
        "label": "16:9 — YouTube / apresentações",
    },
    "square-feed": {
        "width": 1080,
        "height": 1080,
        "label": "1:1 — post de feed",
    },
}


def build_reframe_filter(target: str, strategy: str = "blur-pad") -> str:
    """Return an ffmpeg -vf filter string that reframes the input to `target`.

    Chain this as the FIRST step in the filter graph, before overlays and
    subtitles (subtitles must still be applied last per the hard rules) —
    burning captions before the reframe means they'd get cropped or blurred
    along with the frame.
    """
    if target not in TARGETS:
        available = ", ".join(sorted(TARGETS))
        raise ValueError(f"unknown format target '{target}' — available: {available}")

    w, h = TARGETS[target]["width"], TARGETS[target]["height"]

    if strategy == "crop":
        # Scale so the SHORT side matches, then center-crop the overflow.
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"

    if strategy == "blur-pad":
        # Two copies of the same input, split from one source: a sharp
        # foreground scaled to fit inside the frame, and a background that's
        # scaled to fill + cover, then heavily blurred, to hide the bars.
        return (
            f"split=2[bg][fg];"
            f"[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},gblur=sigma=30[bgblur];"
            f"[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[fgscaled];"
            f"[bgblur][fgscaled]overlay=(W-w)/2:(H-h)/2"
        )

    raise ValueError(f"unknown strategy '{strategy}' — expected 'crop' or 'blur-pad'")


def main() -> None:
    ap = argparse.ArgumentParser(description="Preview the reframe filter for a format target")
    ap.add_argument("--source", type=str, default="1920x1080", help="WxH of the source, e.g. 1920x1080")
    ap.add_argument("--format", type=str, required=True, choices=sorted(TARGETS))
    ap.add_argument("--strategy", type=str, default="blur-pad", choices=["crop", "blur-pad"])
    args = ap.parse_args()

    cfg = TARGETS[args.format]
    print(f"target: {args.format}  ({cfg['label']})  →  {cfg['width']}x{cfg['height']}")
    print(f"strategy: {args.strategy}")
    print()
    print(build_reframe_filter(args.format, args.strategy))


if __name__ == "__main__":
    main()

"""Optional soundtrack layer — mix a music bed under the dialogue.

Deliberately provider-agnostic: it takes any audio file (a track you
licensed, downloaded from a royalty-free library, or generated with
whatever AI music tool you use — Suno included, since Mancia Solutions
already has a Suno workflow running for other projects) and handles the part
that's actually fiddly: looping/trimming it to the video's exact length,
ducking it under speech automatically (so it never fights the dialogue), and
fading it in/out cleanly at the edges.

This is what edvid's "AI soundtrack" phase is, mechanically — the AI part is
the generation step, which happens elsewhere (a separate tool/prompt); what
this script owns is a correct, boring mixdown, and that part shouldn't
depend on which generator produced the track.

Usage:
    python helpers/soundtrack.py --video final.mp4 --music track.mp3 -o with_music.mp4
    python helpers/soundtrack.py --video final.mp4 --music track.mp3 -o out.mp4 --music-db -22 --fade-out 2
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def mix_soundtrack(
    video_path: Path,
    music_path: Path,
    out_path: Path,
    music_db: float = -20.0,
    duck_ratio: float = 6.0,
    fade_out: float = 1.5,
) -> None:
    video_duration = probe_duration(video_path)

    # -stream_loop -1 on the music input loops it indefinitely; -shortest on
    # output trims to the video's length either way, so a short loop or a
    # music file longer than the video both resolve correctly without math.
    filter_complex = (
        f"[2:a]volume={music_db}dB,afade=t=out:st={max(video_duration - fade_out, 0):.2f}:d={fade_out}[music_low];"
        f"[music_low][1:a]sidechaincompress=threshold=0.05:ratio={duck_ratio}:attack=5:release=300[ducked];"
        f"[1:a][ducked]amix=inputs=2:duration=first:dropout_transition=0[aout]"
    )
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(video_path),           # second read of the same file, for its own audio stream in the mix graph
        "-stream_loop", "-1", "-i", str(music_path),
        "-filter_complex", filter_complex,
        "-map", "0:v:0", "-map", "[aout]",
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Mix a music bed under a video's existing dialogue, auto-ducked")
    ap.add_argument("--video", type=Path, required=True)
    ap.add_argument("--music", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--music-db", type=float, default=-20.0, help="Music level relative to dialogue, in dB. More negative = quieter.")
    ap.add_argument("--duck-ratio", type=float, default=6.0, help="How hard the music ducks under speech. Higher = more aggressive duck.")
    ap.add_argument("--fade-out", type=float, default=1.5, help="Seconds of fade-out at the end.")
    args = ap.parse_args()

    if not args.video.exists():
        sys.exit(f"video not found: {args.video}")
    if not args.music.exists():
        sys.exit(f"music file not found: {args.music}")

    mix_soundtrack(args.video, args.music, args.output, args.music_db, args.duck_ratio, args.fade_out)
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()

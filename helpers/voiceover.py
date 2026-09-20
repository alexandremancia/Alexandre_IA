"""Optional narration layer — text-to-speech voiceover via ElevenLabs.

Two real uses, not one:
  1. Replace a bad take's audio entirely (room tone problems, a flub you'd
     rather retype than re-record) while keeping the original video.
  2. Add narration to B-roll/footage that never had spoken audio at all —
     the "faceless content" pattern, script in, voiced video out.

This is opt-in and separate from the main editing pipeline on purpose: it
needs an ElevenLabs API key and a voice_id, and it changes what's actually
being said, which the agent should only ever do on an explicit script the
user reviewed — never as a silent side effect of an edit.

Usage:
    python helpers/voiceover.py --text-file script.txt --voice-id <id> -o narration.wav
    python helpers/voiceover.py --text-file script.txt --voice-id <id> --duck-under original.mp4 -o final.mp4
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import requests

from transcribe_common import load_env_value

TTS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"


def synthesize(text: str, voice_id: str, api_key: str, out_path: Path, stability: float = 0.5, similarity: float = 0.75) -> None:
    resp = requests.post(
        TTS_URL.format(voice_id=voice_id),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": stability, "similarity_boost": similarity},
        },
        timeout=300,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"TTS returned {resp.status_code}: {resp.text[:500]}")
    out_path.write_bytes(resp.content)


def duck_and_mix(video_in: Path, narration_wav: Path, video_out: Path, music_bed: Path | None = None, duck_db: float = -18.0) -> None:
    """Replace (or layer under, if music_bed given) a video's audio with the
    narration track. Ducking applies only to the optional music bed — the
    narration itself is never ducked, it's the thing being heard.
    """
    if music_bed is None:
        cmd = [
            "ffmpeg", "-y", "-i", str(video_in), "-i", str(narration_wav),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(video_out),
        ]
    else:
        # sidechaincompress: the music bed's volume ducks automatically
        # whenever the narration track has signal, then recovers in silence.
        filter_complex = (
            f"[2:a]volume={duck_db}dB[music_low];"
            f"[music_low][1:a]sidechaincompress=threshold=0.05:ratio=8:attack=5:release=300[ducked];"
            f"[1:a][ducked]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
        cmd = [
            "ffmpeg", "-y", "-i", str(video_in), "-i", str(narration_wav), "-i", str(music_bed),
            "-filter_complex", filter_complex,
            "-map", "0:v:0", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(video_out),
        ]
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a TTS narration track and optionally mix it into a video")
    ap.add_argument("--text-file", type=Path, required=True, help="Plain text script to voice")
    ap.add_argument("--voice-id", type=str, required=True, help="ElevenLabs voice ID")
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output path — .wav for narration only, or a video container if --apply-to is set")
    ap.add_argument("--apply-to", type=Path, default=None, help="Video to replace/mix audio into")
    ap.add_argument("--music-bed", type=Path, default=None, help="Optional background music, ducked under the narration")
    ap.add_argument("--stability", type=float, default=0.5)
    ap.add_argument("--similarity", type=float, default=0.75)
    args = ap.parse_args()

    if not args.text_file.exists():
        sys.exit(f"script not found: {args.text_file}")
    text = args.text_file.read_text(encoding="utf-8").strip()
    if not text:
        sys.exit("script is empty")

    api_key = load_env_value("ELEVENLABS_API_KEY", required=True)

    if args.apply_to is None:
        synthesize(text, args.voice_id, api_key, args.output, args.stability, args.similarity)
        print(f"narration saved: {args.output}")
        return

    tmp_wav = args.output.with_suffix(".narration.wav")
    synthesize(text, args.voice_id, api_key, tmp_wav, args.stability, args.similarity)
    duck_and_mix(args.apply_to, tmp_wav, args.output, args.music_bed)
    print(f"final video saved: {args.output}")


if __name__ == "__main__":
    main()

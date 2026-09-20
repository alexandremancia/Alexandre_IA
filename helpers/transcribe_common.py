"""Shared schema, paths and small utilities used by every transcription engine.

Every engine (local WhisperX, ElevenLabs Scribe, or a future one) must write
its transcript as JSON matching this exact shape, because pack_transcripts.py,
render.py and timeline_view.py only ever read `data["words"]`:

    {
      "words": [
        {"type": "word", "text": "Hello", "start": 0.42, "end": 0.61, "speaker_id": "speaker_0"},
        {"type": "spacing", "start": 0.61, "end": 0.68},
        {"type": "word", "text": "world", "start": 0.68, "end": 0.95, "speaker_id": "speaker_0"},
        {"type": "audio_event", "text": "laughter", "start": 3.10, "end": 3.80, "speaker_id": null}
      ],
      "engine": "local-whisperx" | "elevenlabs-scribe",
      "language_code": "pt",
      "num_speakers_hint": 1
    }

`speaker_id` is optional (null/absent when diarization wasn't run — the local
engine only diarizes if `--diarize` is passed and pyannote is installed).
`type: "spacing"` entries are what let pack_transcripts.py and the hard-rule
silence-gap detection in render.py find cut candidates from text alone — an
engine that emits ONLY "word" entries with gaps between end/start is fine too
(both render.py and pack_transcripts.py fall back to inferring the gap from
consecutive word timestamps when no explicit "spacing" entry exists), but
emitting explicit spacing entries is cheap and keeps everything unambiguous.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env_value(key: str, required: bool = False, repo_root: Path | None = None) -> str:
    """Read a key from environment first, then <repo_root>/.env, then ./.env.

    Same lookup order every helper in this skill uses, so a key set any of
    the three ways is picked up consistently.
    """
    v = os.environ.get(key, "")
    if v:
        return v

    candidates = []
    if repo_root is not None:
        candidates.append(repo_root / ".env")
    candidates.append(Path(__file__).resolve().parent.parent / ".env")
    candidates.append(Path(".env"))

    for candidate in candidates:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, val = line.split("=", 1)
                if k.strip() == key:
                    return val.strip().strip('"').strip("'")

    if required:
        import sys
        sys.exit(f"{key} not found in environment or .env")
    return v


def transcript_path(edit_dir: Path, video: Path, audio_track: int = 0) -> Path:
    """Where a video's transcript lands — identical rule for every engine.

    The track belongs in the name, or a rerun with --audio-track hands back
    the transcript of the track it is meant to replace. Track 0 keeps the
    plain name, so transcripts made before the flag existed stay valid.
    """
    suffix = "" if audio_track == 0 else f".track{audio_track}"
    return edit_dir / "transcripts" / f"{video.stem}{suffix}.json"


def count_audio_tracks(video_path: Path) -> int:
    """How many audio streams the container holds."""
    import subprocess
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    return len([ln for ln in out.stdout.splitlines() if ln.strip()])


def extract_audio_wav(video_path: Path, dest: Path, audio_track: int = 0, sample_rate: int = 16000) -> None:
    """Extract mono PCM WAV at the given sample rate — the input every engine wants."""
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-map", f"0:a:{audio_track}",
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def peak_dbfs(wav_path: Path) -> float:
    """Peak level of a 16-bit PCM wav, in dBFS. -inf for digital silence."""
    import array
    import math
    import wave
    peak = 0
    with wave.open(str(wav_path), "rb") as w:
        while frames := w.readframes(1 << 16):
            samples = array.array("h", frames)
            peak = max(peak, max(samples), -min(samples))
    return 20 * math.log10(peak / 32768) if peak > 0 else float("-inf")

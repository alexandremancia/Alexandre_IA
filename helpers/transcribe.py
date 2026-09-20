"""Transcribe a video — engine dispatcher.

Two engines, same output schema (see transcribe_common.py), fully
interchangeable from everything downstream:

  local (DEFAULT)  — WhisperX on your own machine. No API key, no cost,
                      no upload, no size limit, no data leaves your computer.
                      See transcribe_local.py.

  elevenlabs       — ElevenLabs Scribe, cloud. Costs money and needs network,
                      but ships proper speaker diarization and audio-event
                      tags (laughter, applause) without extra setup.
                      See transcribe_elevenlabs.py.

Pick per project, not globally: a solo talking-head video has no reason to
leave your machine; a multi-speaker interview you want tagged with
"(laughter)" and clean diarization out of the box might be worth the cost.

Usage:
    python helpers/transcribe.py <video>                       # local, auto-detect language
    python helpers/transcribe.py <video> --language pt
    python helpers/transcribe.py <video> --engine elevenlabs --num-speakers 2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from transcribe_common import transcript_path  # re-exported for transcribe_batch.py


def transcribe_one(
    video: Path,
    edit_dir: Path,
    engine: str = "local",
    api_key: str | None = None,
    language: str | None = None,
    num_speakers: int | None = None,
    diarize: bool = False,
    model: str = "large-v3",
    verbose: bool = True,
    audio_track: int = 0,
    verbatim: bool = True,
) -> Path:
    """Route to the selected engine. Same signature shape either way so
    transcribe_batch.py doesn't need an if/else of its own."""
    if engine == "local":
        from transcribe_local import transcribe_one_local
        return transcribe_one_local(
            video=video, edit_dir=edit_dir, model_name=model, language=language,
            diarize=diarize, num_speakers=num_speakers, verbose=verbose,
            audio_track=audio_track, verbatim=verbatim,
        )
    elif engine == "elevenlabs":
        from transcribe_elevenlabs import transcribe_one_elevenlabs
        from transcribe_common import load_env_value
        key = api_key or load_env_value("ELEVENLABS_API_KEY", required=True)
        return transcribe_one_elevenlabs(
            video=video, edit_dir=edit_dir, api_key=key, language=language,
            num_speakers=num_speakers, verbose=verbose, audio_track=audio_track,
        )
    else:
        raise ValueError(f"unknown engine '{engine}' — expected 'local' or 'elevenlabs'")


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe a video (local WhisperX by default)")
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, default=None)
    ap.add_argument("--engine", choices=["local", "elevenlabs"], default="local")
    ap.add_argument("--model", type=str, default="large-v3", help="Local engine only: Whisper model size.")
    ap.add_argument("--language", type=str, default=None)
    ap.add_argument("--num-speakers", type=int, default=None)
    ap.add_argument("--diarize", action="store_true", help="Local engine only: also identify speakers.")
    ap.add_argument("--audio-track", type=int, default=0)
    ap.add_argument("--no-verbatim", dest="verbatim", action="store_false",
                     help="Local engine only: disable the filler-preserving initial_prompt.")
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()

    transcribe_one(
        video=video, edit_dir=edit_dir, engine=args.engine, model=args.model,
        language=args.language, num_speakers=args.num_speakers, diarize=args.diarize,
        audio_track=args.audio_track, verbatim=args.verbatim,
    )


if __name__ == "__main__":
    main()

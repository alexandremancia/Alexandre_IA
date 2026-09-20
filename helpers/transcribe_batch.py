"""Batch-transcribe every video in a directory with N parallel workers.

Walks <videos_dir> for common video extensions, transcribes each with the
selected engine (local WhisperX by default — see transcribe.py), writes
transcripts to <videos_dir>/edit/transcripts/<n>.json.

Cached per-file: any source that already has a transcript is skipped.

Note on parallelism and the local engine: WhisperX loads a multi-GB model
per worker. On a single consumer GPU, 4 parallel workers will likely fight
over VRAM and be SLOWER than one worker processing files sequentially — the
--workers default is 1 when --engine local, and 4 when --engine elevenlabs
(a cloud call has no such contention). Raise --workers for local only if you
know your hardware has the headroom (a multi-GPU box, or CPU-only where
workers mostly wait on I/O).

Usage:
    python helpers/transcribe_batch.py <videos_dir>
    python helpers/transcribe_batch.py <videos_dir> --engine elevenlabs --workers 4
    python helpers/transcribe_batch.py <videos_dir> --num-speakers 2 --diarize
"""

from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from transcribe import transcribe_one
from transcribe_common import transcript_path


VIDEO_EXTS = {".mp4", ".MP4", ".mov", ".MOV", ".mkv", ".MKV", ".avi", ".AVI", ".m4v"}


def find_videos(videos_dir: Path) -> list[Path]:
    return sorted(p for p in videos_dir.iterdir() if p.is_file() and p.suffix in VIDEO_EXTS)


def main() -> None:
    ap = argparse.ArgumentParser(description="Parallel batch transcription of a videos directory")
    ap.add_argument("videos_dir", type=Path)
    ap.add_argument("--edit-dir", type=Path, default=None)
    ap.add_argument("--engine", choices=["local", "elevenlabs"], default="local")
    ap.add_argument("--workers", type=int, default=None,
                     help="Default: 1 for local (VRAM contention), 4 for elevenlabs.")
    ap.add_argument("--model", type=str, default="large-v3", help="Local engine only.")
    ap.add_argument("--language", type=str, default=None)
    ap.add_argument("--num-speakers", type=int, default=None)
    ap.add_argument("--diarize", action="store_true", help="Local engine only: also identify speakers.")
    ap.add_argument("--audio-track", type=int, default=0)
    args = ap.parse_args()

    videos_dir = args.videos_dir.resolve()
    if not videos_dir.is_dir():
        sys.exit(f"not a directory: {videos_dir}")

    edit_dir = (args.edit_dir or (videos_dir / "edit")).resolve()
    (edit_dir / "transcripts").mkdir(parents=True, exist_ok=True)

    videos = find_videos(videos_dir)
    if not videos:
        sys.exit(f"no videos found in {videos_dir}")

    workers = args.workers or (1 if args.engine == "local" else 4)

    already_cached = [v for v in videos if transcript_path(edit_dir, v, args.audio_track).exists()]
    pending = [v for v in videos if v not in already_cached]

    print(f"found {len(videos)} videos ({len(already_cached)} cached, {len(pending)} to transcribe) "
          f"— engine={args.engine}, workers={workers}")
    if not pending:
        print("nothing to do")
        return

    t0 = time.time()
    errors: list[tuple[Path, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                transcribe_one,
                video=v, edit_dir=edit_dir, engine=args.engine, model=args.model,
                language=args.language, num_speakers=args.num_speakers,
                diarize=args.diarize, verbose=False, audio_track=args.audio_track,
            ): v
            for v in pending
        }
        for fut in as_completed(futures):
            v = futures[fut]
            try:
                out = fut.result()
                print(f"  + {v.stem}  →  {out.name}")
            except Exception as e:
                errors.append((v, str(e)))
                print(f"  x {v.stem}  FAILED: {e}")

    dt = time.time() - t0
    print(f"\ndone in {dt:.1f}s")
    if errors:
        print(f"{len(errors)} failures:")
        for v, msg in errors:
            print(f"  {v.name}: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()

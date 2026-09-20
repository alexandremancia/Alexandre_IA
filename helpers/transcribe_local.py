"""Transcribe locally with WhisperX — the DEFAULT engine. No API key, no cost,
no upload, no size limit. This is the biggest single upgrade this skill makes
over its ancestor (video-use), which only shipped a cloud engine.

WhisperX does two passes:
  1. Whisper does the actual speech-to-text (fast, but its per-word timestamps
     are decoder *estimates* — often 100-300ms off).
  2. A forced-alignment pass (a wav2vec2 model for the detected language) then
     re-times every word against the raw waveform. This is the step that
     makes word-accurate cuts and karaoke-style captions possible; skipping
     it and using Whisper's own timestamps directly produces visibly wrong
     subtitle timing and cuts that clip the front/back of words.

Output is normalized into the exact schema transcribe_common.py documents,
so pack_transcripts.py, render.py and timeline_view.py need zero changes to
work with either engine.

Hardware notes:
  - NVIDIA GPU: picks CUDA automatically, float16 compute.
  - Apple Silicon: WhisperX's backend (ctranslate2) has no Metal/MPS support
    yet, so it runs on CPU. Slower, but correct. int8 compute type is used
    on CPU to keep it reasonably fast.
  - First run downloads the Whisper model and the alignment model for the
    detected language (a few GB, one time, then cached by huggingface/torch
    in the user's home directory — never re-downloaded after that).

Usage:
    python helpers/transcribe_local.py <video_path>
    python helpers/transcribe_local.py <video_path> --model large-v3 --language pt
    python helpers/transcribe_local.py <video_path> --diarize --num-speakers 2
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

from transcribe_common import (
    count_audio_tracks,
    extract_audio_wav,
    load_env_value,
    peak_dbfs,
    transcript_path,
)


# A known, real limitation of Whisper (not fixed by WhisperX's alignment
# pass, which only re-times whatever text the decoder already produced):
# its language-model prior tends to smooth away disfluencies — "um", "uh",
# false starts, stutters — because its training text underrepresents them.
# That matters here specifically because filler-word removal is one of the
# things this skill does. Priming the decoder with an initial_prompt that
# itself contains disfluencies measurably reduces (does not eliminate) this
# smoothing — a documented community technique, not a WhisperX feature.
# --verbatim is on by default; turn it off with --no-verbatim if a prompt
# ever leaks into the output as hallucinated text (rare, but worth knowing).
VERBATIM_PROMPTS: dict[str, str] = {
    "pt": "É, tipo, hum, então... deixa eu ver, né, tipo assim, hum, é, sei lá.",
    "en": "Um, uh, like, you know, so... let me see, uh, kind of, um, I guess.",
    "es": "Eh, o sea, como que, um, bueno, a ver, eh, digamos, um, no sé.",
}


# Wav2vec2 alignment models WhisperX/HF ships for languages worth naming
# explicitly (WhisperX falls back to a reasonable default for anything else,
# but pinning the ones people will actually use avoids a surprise download
# of the wrong model on first run).
ALIGN_MODEL_HINTS: dict[str, str] = {
    "pt": "jonatasgrosman/wav2vec2-large-xlsr-53-portuguese",
    "en": "WAV2VEC2_ASR_LARGE_LV60K_960H",
    "es": "jonatasgrosman/wav2vec2-large-xlsr-53-spanish",
}


def _pick_device_and_compute() -> tuple[str, str]:
    """CUDA + float16 when available, else CPU + int8 (Apple Silicon included —
    ctranslate2 has no Metal backend, so Apple GPUs are not an option here)."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda", "float16"
    except ImportError:
        pass
    return "cpu", "int8"


def _words_from_aligned_segments(
    segments: list[dict],
    speaker_by_segment: dict[int, str] | None = None,
) -> list[dict]:
    """Flatten WhisperX's aligned segments into the common word-list schema,
    inserting explicit "spacing" entries for every gap between two words so
    silence-gap cut detection works from text alone, same as the Scribe engine.
    """
    words: list[dict] = []
    prev_end: float | None = None

    for seg_idx, seg in enumerate(segments):
        speaker = None
        if speaker_by_segment is not None:
            speaker = speaker_by_segment.get(seg_idx)
        elif "speaker" in seg:
            speaker = seg["speaker"]

        for w in seg.get("words", []):
            # A handful of tokens (bare punctuation, some non-speech markers)
            # don't get a timestamp from the aligner. Skip rather than guess —
            # a wrong timestamp is worse than a dropped stray character.
            start = w.get("start")
            end = w.get("end")
            text = (w.get("word") or "").strip()
            if start is None or end is None or not text:
                continue

            if prev_end is not None and start > prev_end:
                words.append({"type": "spacing", "start": prev_end, "end": start})

            words.append({
                "type": "word",
                "text": text,
                "start": round(float(start), 3),
                "end": round(float(end), 3),
                "speaker_id": speaker,
            })
            prev_end = end

    return words


def _run_diarization(audio_path: Path, num_speakers: int | None, hf_token: str) -> "object":
    import whisperx
    pipeline = whisperx.diarize.DiarizationPipeline(use_auth_token=hf_token, device=_pick_device_and_compute()[0])
    kwargs = {}
    if num_speakers:
        kwargs["min_speakers"] = num_speakers
        kwargs["max_speakers"] = num_speakers
    return pipeline(str(audio_path), **kwargs)


def transcribe_one_local(
    video: Path,
    edit_dir: Path,
    model_name: str = "large-v3",
    language: str | None = None,
    diarize: bool = False,
    num_speakers: int | None = None,
    verbose: bool = True,
    audio_track: int = 0,
    batch_size: int = 16,
    verbatim: bool = True,
) -> Path:
    """Transcribe a single video locally with WhisperX. Returns transcript JSON path. Cached."""
    import whisperx  # imported lazily — this is the heavy dependency, keep it out of the CLI's --help path

    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcript_path(edit_dir, video, audio_track)

    if out_path.exists():
        if verbose:
            print(f"cached: {out_path.name}")
        return out_path

    n_tracks = count_audio_tracks(video)
    if n_tracks > 1 and verbose:
        print(f"  note: {video.name} has {n_tracks} audio tracks, using track "
              f"{audio_track + 1} (--audio-track to change)", flush=True)

    device, compute_type = _pick_device_and_compute()
    t0 = time.time()

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / f"{video.stem}.wav"
        extract_audio_wav(video, wav_path, audio_track)

        peak = peak_dbfs(wav_path)
        if peak < -60.0:
            raise RuntimeError(
                f"track {audio_track + 1} of {video.name} is silent (peak {peak:.1f} dBFS) - "
                + (f"file has {n_tracks} tracks; try --audio-track "
                   + " or ".join(str(i) for i in range(n_tracks) if i != audio_track) + "."
                   if n_tracks > 1 else "check the source audio.")
            )

        if verbose:
            print(f"  loading Whisper ({model_name}, {device}/{compute_type}) — "
                  f"first run downloads the model, then it's cached", flush=True)
        model = whisperx.load_model(model_name, device, compute_type=compute_type, language=language)

        audio = whisperx.load_audio(str(wav_path))

        transcribe_kwargs = {}
        if verbatim and language and language in VERBATIM_PROMPTS:
            transcribe_kwargs["initial_prompt"] = VERBATIM_PROMPTS[language]
        elif verbatim and not language and verbose:
            print("  note: --verbatim works best combined with --language (auto-detect runs "
                  "without the filler-preserving prompt, to avoid biasing language detection)",
                  flush=True)

        if verbose:
            print(f"  transcribing {video.name}", flush=True)
        result = model.transcribe(audio, batch_size=batch_size, language=language, **transcribe_kwargs)
        detected_language = result.get("language", language or "en")

        if verbose:
            print(f"  aligning words against the waveform (language={detected_language})", flush=True)
        align_model, metadata = whisperx.load_align_model(
            language_code=detected_language, device=device,
            model_name=ALIGN_MODEL_HINTS.get(detected_language),
        )
        result = whisperx.align(
            result["segments"], align_model, metadata, audio, device,
            return_char_alignments=False,
        )

        speaker_by_segment: dict[int, str] | None = None
        if diarize:
            hf_token = load_env_value("HF_TOKEN")
            if not hf_token:
                if verbose:
                    print("  --diarize requested but HF_TOKEN is not set — skipping diarization. "
                          "Get a free token at https://huggingface.co/settings/tokens and accept "
                          "the pyannote/speaker-diarization model terms.", flush=True)
            else:
                if verbose:
                    print("  diarizing speakers", flush=True)
                diarize_segments = _run_diarization(wav_path, num_speakers, hf_token)
                result = whisperx.assign_word_speakers(diarize_segments, result)
                speaker_by_segment = {
                    i: seg.get("speaker") for i, seg in enumerate(result["segments"])
                }

    words = _words_from_aligned_segments(result["segments"], speaker_by_segment)
    payload = {
        "words": words,
        "engine": "local-whisperx",
        "language_code": detected_language,
        "num_speakers_hint": num_speakers,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    dt = time.time() - t0

    if verbose:
        kb = out_path.stat().st_size / 1024
        print(f"  saved: {out_path.name} ({kb:.1f} KB) in {dt:.1f}s — {len(words)} tokens")

    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe a video locally with WhisperX (default engine)")
    ap.add_argument("video", type=Path)
    ap.add_argument("--edit-dir", type=Path, default=None)
    ap.add_argument("--model", type=str, default="large-v3",
                     help="Whisper model size: tiny/base/small/medium/large-v2/large-v3. "
                          "Bigger is more accurate and slower. large-v3 is the default; "
                          "drop to 'medium' on modest hardware without a GPU.")
    ap.add_argument("--language", type=str, default=None, help="ISO code, e.g. 'pt'. Omit to auto-detect.")
    ap.add_argument("--diarize", action="store_true", help="Also identify who's speaking (needs HF_TOKEN).")
    ap.add_argument("--num-speakers", type=int, default=None)
    ap.add_argument("--audio-track", type=int, default=0)
    ap.add_argument("--batch-size", type=int, default=16, help="Lower this (e.g. 4) if you hit an out-of-memory error.")
    ap.add_argument("--no-verbatim", dest="verbatim", action="store_false",
                     help="Disable the filler-preserving initial_prompt (see module docstring).")
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()

    transcribe_one_local(
        video=video, edit_dir=edit_dir, model_name=args.model, language=args.language,
        diarize=args.diarize, num_speakers=args.num_speakers, audio_track=args.audio_track,
        batch_size=args.batch_size, verbatim=args.verbatim,
    )


if __name__ == "__main__":
    main()

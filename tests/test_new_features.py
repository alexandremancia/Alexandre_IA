"""Tests for everything added on top of the video-use base: caption presets,
format targets, the local transcription schema, and the parameterized
build_master_srt (max_words/uppercase instead of hardcoded 2/True).
"""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

# The helpers import each other by bare name (`from transcribe_common import ...`),
# which resolves naturally when they're run as `python helpers/<name>.py` because
# the script's own directory lands on sys.path. Loading them via importlib from
# the test suite doesn't get that for free, so put helpers/ on the path here.
HELPERS_DIR = Path(__file__).parents[1] / "helpers"
if str(HELPERS_DIR) not in sys.path:
    sys.path.insert(0, str(HELPERS_DIR))


def _load(name: str, rel_path: str):
    module_path = Path(__file__).parents[1] / rel_path
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


captions_presets = _load("captions_presets", "helpers/captions_presets.py")
format_targets = _load("format_targets", "helpers/format_targets.py")
transcribe_local = _load("transcribe_local", "helpers/transcribe_local.py")
render = _load("render", "helpers/render.py")


class CaptionPresetsTests(unittest.TestCase):
    def test_all_presets_have_required_keys(self):
        for name, cfg in captions_presets.PRESETS.items():
            with self.subTest(preset=name):
                self.assertIn("max_words", cfg)
                self.assertIn("uppercase", cfg)
                self.assertIn("base_style", cfg)
                self.assertIn("margin_v_vertical", cfg)
                self.assertIn("margin_v_horizontal", cfg)
                self.assertIsInstance(cfg["max_words"], int)
                self.assertGreater(cfg["max_words"], 0)

    def test_vertical_margin_clears_platform_ui_and_exceeds_horizontal(self):
        """Vertical platforms (Reels/TikTok/Shorts) overlay roughly the bottom
        25-30% of the frame with UI. Every preset must sit above that, and
        above its own horizontal margin."""
        for name, cfg in captions_presets.PRESETS.items():
            with self.subTest(preset=name):
                frac = cfg["margin_v_vertical"] / captions_presets.PLAY_RES_Y
                self.assertGreaterEqual(frac, 0.28, "legenda cairia atras da UI vertical")
                self.assertLess(frac, 0.45, "legenda alta demais, perto do centro do quadro")
                self.assertGreater(cfg["margin_v_vertical"], cfg["margin_v_horizontal"])

    def test_force_style_picks_margin_by_format(self):
        vertical = captions_presets.force_style_for("bold-overlay", "vertical-reel")
        horizontal = captions_presets.force_style_for("bold-overlay", "horizontal-youtube")
        none_given = captions_presets.force_style_for("bold-overlay", None)
        self.assertIn("MarginV=90", vertical)
        self.assertIn("MarginV=34", horizontal)
        # sem --format, cai no horizontal (padrao mais seguro)
        self.assertEqual(none_given, horizontal)

    def test_unknown_preset_raises(self):
        with self.assertRaises(ValueError):
            captions_presets.get_preset("does-not-exist")

    def test_default_preset_is_valid(self):
        self.assertIn(captions_presets.DEFAULT_PRESET, captions_presets.PRESETS)


class FormatTargetsTests(unittest.TestCase):
    def test_all_targets_produce_a_filter_for_both_strategies(self):
        for target in format_targets.TARGETS:
            for strategy in ("crop", "blur-pad"):
                with self.subTest(target=target, strategy=strategy):
                    f = format_targets.build_reframe_filter(target, strategy)
                    self.assertIsInstance(f, str)
                    self.assertGreater(len(f), 0)

    def test_vertical_reel_dimensions(self):
        cfg = format_targets.TARGETS["vertical-reel"]
        self.assertEqual((cfg["width"], cfg["height"]), (1080, 1920))

    def test_unknown_target_raises(self):
        with self.assertRaises(ValueError):
            format_targets.build_reframe_filter("not-a-real-target")

    def test_unknown_strategy_raises(self):
        with self.assertRaises(ValueError):
            format_targets.build_reframe_filter("vertical-reel", strategy="teleport")


class LocalTranscriptionSchemaTests(unittest.TestCase):
    def test_flattens_to_common_schema_with_spacing_gaps(self):
        segments = [
            {"words": [
                {"word": "Olá,", "start": 0.10, "end": 0.45},
                {"word": "mundo.", "start": 0.50, "end": 0.95},
            ]},
            {"words": [
                {"word": "Segunda", "start": 1.60, "end": 1.90},
            ]},
        ]
        words = transcribe_local._words_from_aligned_segments(segments)
        types = [w["type"] for w in words]
        self.assertEqual(types, ["word", "spacing", "word", "spacing", "word"])
        self.assertEqual(words[0]["text"], "Olá,")
        # gap between 0.95 and 1.60 must be captured
        gap = next(w for w in words if w["type"] == "spacing" and w["start"] == 0.95)
        self.assertEqual(gap["end"], 1.60)

    def test_skips_words_with_no_timestamp(self):
        segments = [{"words": [
            {"word": "ok", "start": 0.0, "end": 0.2},
            {"word": ","},  # no start/end — aligner sometimes drops these
        ]}]
        words = transcribe_local._words_from_aligned_segments(segments)
        self.assertEqual(len(words), 1)

    def test_speaker_id_carried_from_segment(self):
        segments = [{"words": [{"word": "oi", "start": 0.0, "end": 0.3}]}]
        words = transcribe_local._words_from_aligned_segments(segments, speaker_by_segment={0: "speaker_1"})
        self.assertEqual(words[0]["speaker_id"], "speaker_1")


class BuildMasterSrtParametrizedTests(unittest.TestCase):
    def _make_edit_dir(self, tmp_path: Path, words: list[dict]) -> Path:
        edit_dir = tmp_path / "edit"
        (edit_dir / "transcripts").mkdir(parents=True)
        (edit_dir / "transcripts" / "clip01.json").write_text(json.dumps({"words": words}))
        return edit_dir

    def test_default_matches_original_two_word_uppercase_behavior(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            words = [
                {"type": "word", "text": "hello", "start": 0.0, "end": 0.3},
                {"type": "word", "text": "world", "start": 0.35, "end": 0.6},
                {"type": "word", "text": "again", "start": 0.65, "end": 0.9},
            ]
            edit_dir = self._make_edit_dir(tmp_path, words)
            edl = {"sources": {"clip01": "x"}, "ranges": [{"source": "clip01", "start": 0.0, "end": 1.0}]}
            out = edit_dir / "master.srt"
            render.build_master_srt(edl, edit_dir, out)  # no max_words/uppercase passed
            content = out.read_text()
            self.assertIn("HELLO WORLD", content)  # 2-word chunk, uppercase — original default preserved
            self.assertIn("AGAIN", content)

    def test_natural_sentence_style_is_not_uppercase_and_chunks_wider(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            words = [
                {"type": "word", "text": "hello", "start": 0.0, "end": 0.3},
                {"type": "word", "text": "world", "start": 0.35, "end": 0.6},
                {"type": "word", "text": "again", "start": 0.65, "end": 0.9},
            ]
            edit_dir = self._make_edit_dir(tmp_path, words)
            edl = {"sources": {"clip01": "x"}, "ranges": [{"source": "clip01", "start": 0.0, "end": 1.0}]}
            out = edit_dir / "master.srt"
            render.build_master_srt(edl, edit_dir, out, max_words=10, uppercase=False)
            content = out.read_text()
            self.assertIn("hello world again", content)  # single chunk, natural case
            self.assertNotIn("HELLO", content)


if __name__ == "__main__":
    unittest.main()

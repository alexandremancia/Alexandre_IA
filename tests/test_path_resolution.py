"""Regression tests for EDL path resolution.

SKILL.md documents an EDL's `overlays[].file` and `subtitles` entries in the
`edit/animations/...` / `edit/master.srt` form — relative to the videos dir.
But the EDL itself lives in `<videos_dir>/edit/`, so resolving those against
the EDL's own directory yields `<videos_dir>/edit/edit/...`. That crashed the
overlay composite and silently dropped subtitles from the render.
"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

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


render = _load("render", "helpers/render.py")


class TestResolvePath(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.videos_dir = Path(self._tmp.name).resolve()
        self.edit_dir = self.videos_dir / "edit"
        (self.edit_dir / "animations" / "slot_1").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def test_absolute_path_passes_through(self):
        target = self.videos_dir / "clip01.mp4"
        target.write_text("x")
        self.assertEqual(render.resolve_path(str(target), self.edit_dir), target)

    def test_path_relative_to_edit_dir_still_wins(self):
        """The pre-existing convention must keep working unchanged."""
        target = self.edit_dir / "master.srt"
        target.write_text("x")
        self.assertEqual(render.resolve_path("master.srt", self.edit_dir), target)

    def test_videos_dir_relative_path_from_skill_md_resolves(self):
        """`edit/master.srt` must not become `edit/edit/master.srt`."""
        target = self.edit_dir / "master.srt"
        target.write_text("x")
        resolved = render.resolve_path("edit/master.srt", self.edit_dir)
        self.assertEqual(resolved, target)
        self.assertTrue(resolved.exists())

    def test_videos_dir_relative_overlay_resolves(self):
        target = self.edit_dir / "animations" / "slot_1" / "render.mp4"
        target.write_text("x")
        resolved = render.resolve_path(
            "edit/animations/slot_1/render.mp4", self.edit_dir
        )
        self.assertEqual(resolved, target)

    def test_edit_dir_candidate_wins_when_both_exist(self):
        """Ambiguity resolves toward the EDL's own directory, not the parent."""
        near = self.edit_dir / "master.srt"
        far = self.videos_dir / "master.srt"
        near.write_text("near")
        far.write_text("far")
        self.assertEqual(render.resolve_path("master.srt", self.edit_dir), near)

    def test_missing_path_reports_edit_dir_candidate(self):
        """Nothing on disk → report the path the EDL author most likely meant."""
        resolved = render.resolve_path("ausente.srt", self.edit_dir)
        self.assertEqual(resolved, self.edit_dir / "ausente.srt")


if __name__ == "__main__":
    unittest.main()

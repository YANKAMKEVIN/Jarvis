import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from jarvis.capabilities.notes import NotesCapability


class FixedClock:
    def __call__(self):
        return datetime(2026, 10, 16, 9, 30, 0)


class SaveNoteTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp()) / "notes"
        self.cap = NotesCapability(notes_dir=self.dir, clock=FixedClock())

    def test_saves_with_title(self):
        result = self.cap.save_note("Acheter du pain.", "Courses")
        self.assertTrue(result.ok)
        path = Path(result.data["path"])
        self.assertTrue(path.exists())
        self.assertIn("courses", path.name)
        content = path.read_text(encoding="utf-8")
        self.assertIn("# Courses", content)
        self.assertIn("Acheter du pain.", content)

    def test_saves_without_title(self):
        result = self.cap.save_note("Juste une pensee.")
        self.assertTrue(result.ok)
        self.assertTrue(Path(result.data["path"]).exists())

    def test_empty_rejected(self):
        self.assertFalse(self.cap.save_note("   ").ok)

    def test_too_long_rejected(self):
        result = self.cap.save_note("x" * 20001)
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_text")

    def test_list_notes(self):
        self.cap.save_note("Une", "a")
        self.cap.save_note("Deux", "b")
        result = self.cap.list_notes()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 2)

    def test_list_empty_when_no_dir(self):
        cap = NotesCapability(notes_dir=Path(tempfile.mkdtemp()) / "absent")
        result = cap.list_notes()
        self.assertTrue(result.ok)
        self.assertEqual(result.data["count"], 0)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from jarvis.capabilities.memory import MemoryCapability
from jarvis.memory.store import MemoryStore


class PreferredTests(unittest.TestCase):
    def _cap(self):
        return MemoryCapability(MemoryStore(Path(tempfile.mkdtemp()) / "memory.db"))

    def test_returns_stored_preference(self):
        cap = self._cap()
        cap.remember("preference", "actualites", "tech")
        self.assertEqual(cap.preferred("actualites"), "tech")

    def test_missing_preference_returns_none(self):
        self.assertIsNone(self._cap().preferred("actualites"))

    def test_blank_subject_returns_none(self):
        self.assertIsNone(self._cap().preferred("   "))


if __name__ == "__main__":
    unittest.main()

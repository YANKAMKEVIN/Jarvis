import asyncio
import tempfile
import unittest
from pathlib import Path

from jarvis.live.registry import create_live_registry
from jarvis.macros import MacroError, MacroStore


def store():
    return MacroStore(path=Path(tempfile.mkdtemp()) / "macros.db")


class MacroStoreTests(unittest.TestCase):
    def test_save_get_list_delete(self):
        s = store()
        row = s.save("Reunion", "ouvre Zoom et prepare un message a l'equipe")
        self.assertEqual(row["name"], "Reunion")
        self.assertEqual(s.get("reunion")["goal"], "ouvre Zoom et prepare un message a l'equipe")
        self.assertEqual(len(s.list()), 1)
        self.assertTrue(s.delete("REUNION"))  # case-insensitive key
        self.assertIsNone(s.get("reunion"))
        self.assertFalse(s.delete("reunion"))

    def test_upsert_same_name(self):
        s = store()
        s.save("x", "goal 1")
        s.save("x", "goal 2")
        self.assertEqual(len(s.list()), 1)
        self.assertEqual(s.get("x")["goal"], "goal 2")

    def test_validation(self):
        s = store()
        with self.assertRaises(MacroError):
            s.save("  ", "goal")
        with self.assertRaises(MacroError):
            s.save("name", "   ")


class FakeMemory:
    def log_action(self, *a, **k):
        return None


class MacroToolsTests(unittest.TestCase):
    def _tools(self):
        s = store()
        registry = create_live_registry(macro_store=s, memory_capability=FakeMemory())
        return {t.info.name: t for t in registry.livekit_tools()}, s

    def test_save_then_list_then_delete(self):
        tools, s = self._tools()
        saved = asyncio.run(tools["save_macro"]("Focus", "mets ne pas deranger"))
        self.assertTrue(saved["ok"])

        listed = asyncio.run(tools["list_macros"]())
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["macros"][0]["name"], "Focus")

        deleted = asyncio.run(tools["delete_macro"]("Focus"))
        self.assertTrue(deleted["ok"])

    def test_run_unknown_macro(self):
        tools, s = self._tools()
        result = asyncio.run(tools["run_macro"]("inexistante"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "macro_not_found")


if __name__ == "__main__":
    unittest.main()

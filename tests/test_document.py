import tempfile
import unittest
from pathlib import Path

from jarvis.capabilities.document import DocumentCapability
from jarvis.tools.filesystem import FileSystemError, FileSystemTools, PathResolver


class ModelTurn:
    def __init__(self, text):
        self.text = text
        self.tool_calls = []


class FakeModel:
    def __init__(self, text="REPONSE", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return ModelTurn(self.text)


def tools_in(home):
    return FileSystemTools(resolver=PathResolver(home=home))


class ReadTextTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()

    def test_reads_text(self):
        f = Path(self.home) / "note.txt"
        f.write_text("Budget 2026 : 1000 euros")
        state = tools_in(self.home).read_text("note.txt")
        self.assertIn("Budget 2026", state["text"])
        self.assertFalse(state["truncated"])

    def test_truncates(self):
        f = Path(self.home) / "big.txt"
        f.write_text("x" * 50000)
        state = tools_in(self.home).read_text("big.txt", max_chars=1000)
        self.assertEqual(state["char_count"], 1000)
        self.assertTrue(state["truncated"])

    def test_binary_refused(self):
        f = Path(self.home) / "bin.dat"
        f.write_bytes(b"PK\x00\x01\x02binary")
        with self.assertRaises(FileSystemError) as ctx:
            tools_in(self.home).read_text("bin.dat")
        self.assertEqual(ctx.exception.code, "binary_file")


class DocumentQaTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        (Path(self.home) / "contrat.txt").write_text("Le contrat se termine le 31 decembre 2026.")

    def _cap(self, model):
        return DocumentCapability(tools_in(self.home), model=model)

    def test_answers_from_document(self):
        model = FakeModel(text="Le 31 decembre 2026.")
        result = self._cap(model).ask("contrat.txt", "Quand se termine le contrat ?")
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Le 31 decembre 2026.")
        # The document text reached the model.
        self.assertIn("31 decembre 2026", model.calls[0][-1]["content"])

    def test_missing_file(self):
        result = self._cap(FakeModel()).ask("absent.txt", "quoi ?")
        self.assertFalse(result.ok)

    def test_empty_question(self):
        result = self._cap(FakeModel()).ask("contrat.txt", "  ")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_question")

    def test_model_error(self):
        result = self._cap(FakeModel(error=RuntimeError("down"))).ask("contrat.txt", "quoi ?")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "model_error")


if __name__ == "__main__":
    unittest.main()

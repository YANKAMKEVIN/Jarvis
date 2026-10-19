import os
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


class RemoteModel(FakeModel):
    """A planner model whose content goes off this machine."""

    def __init__(self, base_url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", **kw):
        super().__init__(**kw)
        self.base_url = base_url


class LocalEndpointModel(FakeModel):
    def __init__(self, url="http://localhost:11434/api/chat", **kw):
        super().__init__(**kw)
        self.url = url


class RemoteModelGuardTests(unittest.TestCase):
    """Document content must not reach a non-local planner model by default."""

    def setUp(self):
        self.home = tempfile.mkdtemp()
        (Path(self.home) / "a.txt").write_text("Decision : reporter au 5 novembre. Action : preparer le budget.")
        (Path(self.home) / "b.txt").write_text("Decision : reporter au 5 novembre. Action : revoir le planning.")
        self._saved = os.environ.pop("JARVIS_DOCUMENT_ALLOW_REMOTE", None)

    def tearDown(self):
        os.environ.pop("JARVIS_DOCUMENT_ALLOW_REMOTE", None)
        if self._saved is not None:
            os.environ["JARVIS_DOCUMENT_ALLOW_REMOTE"] = self._saved

    def _cap(self, model):
        return DocumentCapability(tools_in(self.home), model=model)

    def test_remote_model_blocks_ask(self):
        model = RemoteModel(text="x")
        result = self._cap(model).ask("a.txt", "quoi ?")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "remote_model_blocked")
        self.assertEqual(model.calls, [])  # nothing was sent

    def test_remote_model_blocks_compare_and_extract(self):
        self.assertEqual(self._cap(RemoteModel()).compare("a.txt", "b.txt").error_code, "remote_model_blocked")
        self.assertEqual(self._cap(RemoteModel()).extract_actions("a.txt").error_code, "remote_model_blocked")

    def test_remote_ollama_host_is_blocked(self):
        model = LocalEndpointModel(url="http://192.168.1.50:11434/api/chat")
        self.assertEqual(self._cap(model).ask("a.txt", "quoi ?").error_code, "remote_model_blocked")

    def test_loopback_endpoint_is_allowed(self):
        model = LocalEndpointModel(text="Le 5 novembre.")
        result = self._cap(model).ask("a.txt", "quand ?")
        self.assertTrue(result.ok)
        self.assertEqual(len(model.calls), 1)  # content reached the local model

    def test_injected_model_without_endpoint_is_allowed(self):
        # Keeps every other test (plain FakeModel) working: no url/base_url = local.
        self.assertTrue(self._cap(FakeModel(text="ok")).ask("a.txt", "quand ?").ok)

    def test_opt_in_allows_remote(self):
        os.environ["JARVIS_DOCUMENT_ALLOW_REMOTE"] = "oui"
        model = RemoteModel(text="Le 5 novembre.")
        result = self._cap(model).ask("a.txt", "quand ?")
        self.assertTrue(result.ok)
        self.assertEqual(len(model.calls), 1)


if __name__ == "__main__":
    unittest.main()

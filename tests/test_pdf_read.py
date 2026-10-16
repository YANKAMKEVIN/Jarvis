import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jarvis.capabilities.document import DocumentCapability
from jarvis.tools.filesystem import FileSystemError, FileSystemTools, PathResolver


class FakePage:
    def __init__(self, text):
        self._text = text

    def extract_text(self):
        return self._text


class FakeReader:
    def __init__(self, path):
        self.pages = [
            FakePage("Le contrat se termine le 31 decembre 2026."),
            FakePage("Clause 2 : paiement sous 30 jours."),
        ]


class ModelTurn:
    def __init__(self, text):
        self.text = text
        self.tool_calls = []


class FakeModel:
    def __init__(self, text="REPONSE"):
        self.text = text
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append(messages)
        return ModelTurn(self.text)


def tools_in(home):
    return FileSystemTools(resolver=PathResolver(home=home))


class PdfReadTests(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.pdf = Path(self.home) / "contrat.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 fake bytes")  # content irrelevant (reader faked)

    def test_extracts_pdf_text(self):
        with patch("pypdf.PdfReader", FakeReader):
            state = tools_in(self.home).read_text("contrat.pdf")
        self.assertIn("31 decembre 2026", state["text"])
        self.assertIn("paiement sous 30 jours", state["text"])

    def test_document_qa_over_pdf(self):
        model = FakeModel(text="Le 31 decembre 2026.")
        cap = DocumentCapability(tools_in(self.home), model=model)
        with patch("pypdf.PdfReader", FakeReader):
            result = cap.ask("contrat.pdf", "Quand se termine le contrat ?")
        self.assertTrue(result.ok)
        self.assertIn("31 decembre 2026", model.calls[0][-1]["content"])  # pdf text reached model

    def test_unreadable_pdf_raises(self):
        def boom(path):
            raise ValueError("corrupt")

        with patch("pypdf.PdfReader", boom):
            with self.assertRaises(FileSystemError) as ctx:
                tools_in(self.home).read_text("contrat.pdf")
        self.assertEqual(ctx.exception.code, "pdf_unreadable")


if __name__ == "__main__":
    unittest.main()

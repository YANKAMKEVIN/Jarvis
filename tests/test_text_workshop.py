import unittest

from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.text_workshop import TextWorkshopCapability


class ModelTurn:
    def __init__(self, text):
        self.text = text
        self.tool_calls = []


class FakeModel:
    def __init__(self, text="RESULT", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append((messages, tools))
        if self.error:
            raise self.error
        return ModelTurn(self.text)


class FakeClipboard:
    def __init__(self, text="bonjour", has_text=True, truncated=False):
        self._get = ToolResult.success(
            action="get_clipboard_text", message="ok",
            has_text=has_text, text=text, truncated=truncated,
        )
        self.set_calls = []

    def get_clipboard_text(self):
        return self._get

    def set_clipboard_text(self, text):
        self.set_calls.append(text)
        return ToolResult.success(
            action="set_clipboard_text", message="ok", state_confirmed=True,
        )


class TextWorkshopTests(unittest.TestCase):
    def test_transforms_and_writes_back(self):
        clip = FakeClipboard(text="hello")
        model = FakeModel(text="Bonjour")
        cap = TextWorkshopCapability(clip, model=model)

        result = cap.rewrite_clipboard("traduis en francais")

        self.assertTrue(result.ok)
        self.assertEqual(clip.set_calls, ["Bonjour"])
        self.assertEqual(result.data["transformed_length"], len("Bonjour"))
        # The source text and instruction reach the model.
        sent = model.calls[0][0]
        self.assertIn("hello", sent[-1]["content"])
        self.assertIn("traduis en francais", sent[-1]["content"])

    def test_empty_instruction_rejected(self):
        cap = TextWorkshopCapability(FakeClipboard(), model=FakeModel())
        result = cap.rewrite_clipboard("   ")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "invalid_instruction")

    def test_empty_clipboard_rejected(self):
        cap = TextWorkshopCapability(FakeClipboard(has_text=False), model=FakeModel())
        result = cap.rewrite_clipboard("corrige")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "empty_clipboard")

    def test_truncated_clipboard_refused(self):
        cap = TextWorkshopCapability(FakeClipboard(truncated=True), model=FakeModel())
        result = cap.rewrite_clipboard("corrige")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "clipboard_too_long")

    def test_model_error_handled(self):
        cap = TextWorkshopCapability(FakeClipboard(), model=FakeModel(error=RuntimeError("down")))
        result = cap.rewrite_clipboard("corrige")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "model_error")

    def test_empty_model_output_not_written(self):
        clip = FakeClipboard()
        cap = TextWorkshopCapability(clip, model=FakeModel(text="   "))
        result = cap.rewrite_clipboard("corrige")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "empty_result")
        self.assertEqual(clip.set_calls, [])  # nothing written


if __name__ == "__main__":
    unittest.main()

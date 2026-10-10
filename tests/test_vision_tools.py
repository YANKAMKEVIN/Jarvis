import os
import unittest
from unittest.mock import patch

from jarvis.tools.vision import VisionError, VisionTools


class RecordingTransport:
    def __init__(self, text="Une analyse.", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def __call__(self, model, image_bytes, mime_type, prompt):
        self.calls.append((model, len(image_bytes), mime_type, prompt))

        if self.error is not None:
            raise self.error

        return self.text


def make_tools(transport, image=b"PNGDATA", model="gemini-2.5-flash", **kwargs):
    return VisionTools(
        transport=transport,
        model=model,
        file_reader=lambda _path: image,
        clock=iter([1.0, 1.25]).__next__,
        **kwargs,
    )


class VisionToolsTest(unittest.TestCase):
    def test_analyze_success_returns_structured_metadata(self):
        transport = RecordingTransport(text="  Il y a une page web.  ")
        tools = make_tools(transport)

        result = tools.analyze("/x/jarvis-shot.png", "Decris l'ecran.")

        self.assertEqual(result["analysis"], "Il y a une page web.")
        self.assertEqual(result["model"], "gemini-2.5-flash")
        self.assertEqual(result["image_bytes"], len(b"PNGDATA"))
        self.assertEqual(result["mime_type"], "image/png")
        self.assertEqual(result["duration_ms"], 250)
        # PNG sent as-is, no JPEG conversion.
        self.assertEqual(transport.calls[0][2], "image/png")

    def test_analyze_rejects_blank_prompt(self):
        tools = make_tools(RecordingTransport())

        with self.assertRaises(VisionError) as ctx:
            tools.analyze("/x/shot.png", "   ")

        self.assertEqual(ctx.exception.code, "invalid_prompt")

    def test_unreadable_image_raises(self):
        def reader(_path):
            raise OSError("missing")

        tools = VisionTools(transport=RecordingTransport(), file_reader=reader)

        with self.assertRaises(VisionError) as ctx:
            tools.analyze("/x/shot.png", "Decris.")

        self.assertEqual(ctx.exception.code, "image_unreadable")

    def test_empty_image_bytes_raises(self):
        tools = make_tools(RecordingTransport(), image=b"")

        with self.assertRaises(VisionError) as ctx:
            tools.analyze("/x/shot.png", "Decris.")

        self.assertEqual(ctx.exception.code, "image_unreadable")

    def test_image_too_large_is_refused_without_downscaling(self):
        transport = RecordingTransport()
        tools = make_tools(transport, image=b"X" * 50, max_image_bytes=10)

        with self.assertRaises(VisionError) as ctx:
            tools.analyze("/x/shot.png", "Decris.")

        self.assertEqual(ctx.exception.code, "image_too_large")
        self.assertEqual(transport.calls, [])  # never sent

    def test_empty_analysis_is_honest_failure(self):
        tools = make_tools(RecordingTransport(text="   "))

        with self.assertRaises(VisionError) as ctx:
            tools.analyze("/x/shot.png", "Decris.")

        self.assertEqual(ctx.exception.code, "empty_analysis")

    def test_transport_exception_is_wrapped(self):
        tools = make_tools(RecordingTransport(error=RuntimeError("boom")))

        with self.assertRaises(VisionError) as ctx:
            tools.analyze("/x/shot.png", "Decris.")

        self.assertEqual(ctx.exception.code, "vision_request_failed")

    def test_default_transport_requires_api_key(self):
        # No transport injected: the default path must refuse without a key,
        # before building any client or making a request.
        tools = VisionTools(
            model="gemini-2.5-flash",
            api_key_env="JARVIS_VISION_TEST_MISSING_KEY",
            file_reader=lambda _path: b"PNGDATA",
        )

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(VisionError) as ctx:
                tools.analyze("/x/shot.png", "Decris.")

        self.assertEqual(ctx.exception.code, "vision_api_key_missing")


if __name__ == "__main__":
    unittest.main()

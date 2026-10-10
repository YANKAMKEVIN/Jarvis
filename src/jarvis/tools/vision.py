from __future__ import annotations

import os
import time
from typing import Any, Callable


DEFAULT_VISION_MODEL = "gemini-2.5-flash"
DEFAULT_API_KEY_ENV = "GOOGLE_API_KEY"

# Inline request payloads are capped by the Gemini API (~20 MB total). A full
# Retina PNG (e.g. 3024x1964) is a few MB and sent as-is: NO downscaling and NO
# JPEG re-encoding, so small interface text stays legible. Anything above this
# is refused with a clear error rather than silently truncated or shrunk.
MAX_IMAGE_BYTES = 18 * 1024 * 1024

_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

# Transport contract: a callable (model, image_bytes, mime_type, prompt) -> str.
# Injectable so analysis flows are fully testable without any network call.
VisionTransport = Callable[[str, bytes, str, str], str]


class VisionError(Exception):
    def __init__(self, message: str, code: str | None = None, data: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data or {}


class VisionTools:
    def __init__(
        self,
        transport: VisionTransport | None = None,
        model: str | None = None,
        api_key_env: str = DEFAULT_API_KEY_ENV,
        max_image_bytes: int = MAX_IMAGE_BYTES,
        file_reader: Callable[[str], bytes] | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.transport = transport if transport is not None else self._default_transport
        self.model = model or DEFAULT_VISION_MODEL
        self.api_key_env = api_key_env
        self.max_image_bytes = int(max_image_bytes)
        self.file_reader = file_reader if file_reader is not None else self._default_file_reader
        self.clock = clock if clock is not None else time.monotonic

    def analyze(self, image_path: str, prompt: str) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise VisionError("La consigne d'analyse est vide.", code="invalid_prompt")

        image_bytes = self._read_image(image_path)
        size = len(image_bytes)

        if size == 0:
            raise VisionError(
                "La capture est vide, analyse impossible.",
                code="image_unreadable",
            )

        if size > self.max_image_bytes:
            raise VisionError(
                "La capture est trop lourde pour l'analyse. Capture une fenetre "
                "ou une region plus petite.",
                code="image_too_large",
                data={"image_bytes": size, "max_image_bytes": self.max_image_bytes},
            )

        mime_type = self._mime_for(image_path)
        start = self.clock()

        try:
            text = self.transport(self.model, image_bytes, mime_type, prompt)
        except VisionError:
            raise
        except Exception as error:
            raise VisionError(
                f"L'analyse visuelle a echoue : {error}",
                code="vision_request_failed",
            ) from error

        duration_ms = int((self.clock() - start) * 1000)

        if not isinstance(text, str) or not text.strip():
            raise VisionError(
                "Le modele n'a renvoye aucune analyse.",
                code="empty_analysis",
                data={"duration_ms": duration_ms},
            )

        return {
            "analysis": text.strip(),
            "model": self.model,
            "image_bytes": size,
            "mime_type": mime_type,
            "duration_ms": duration_ms,
        }

    def _read_image(self, image_path: str) -> bytes:
        if not isinstance(image_path, str) or not image_path.strip():
            raise VisionError("Chemin de capture invalide.", code="image_unreadable")

        try:
            return self.file_reader(image_path)
        except OSError as error:
            raise VisionError(
                "La capture est introuvable ou illisible.",
                code="image_unreadable",
                data={"error": str(error)},
            ) from error

    @staticmethod
    def _mime_for(image_path: str) -> str:
        _root, suffix = os.path.splitext(image_path.lower())
        return _MIME_BY_SUFFIX.get(suffix, "image/png")

    @staticmethod
    def _default_file_reader(image_path: str) -> bytes:
        with open(image_path, "rb") as handle:
            return handle.read()

    def _default_transport(
        self,
        model: str,
        image_bytes: bytes,
        mime_type: str,
        prompt: str,
    ) -> str:
        api_key = os.environ.get(self.api_key_env)

        if not api_key:
            raise VisionError(
                f"La cle {self.api_key_env} est absente pour l'analyse visuelle.",
                code="vision_api_key_missing",
            )

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
        )
        return (getattr(response, "text", None) or "").strip()

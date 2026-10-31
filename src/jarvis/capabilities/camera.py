"""Look through the camera on request: one still, described, then deleted.

Same contract as screen vision: observe only, report what is visible, never
invent. The still is sent to the vision model exactly like a screen capture
and removed right after, whatever happens. People may be described (posture,
clothing, expression) but never identified.
"""

from __future__ import annotations

from pathlib import Path

from jarvis.capabilities.results import ToolResult
from jarvis.tools.camera import CameraCapture, CameraError
from jarvis.tools.vision import VisionError, VisionTools

_CAMERA_RULES = (
    "Tu analyses une photo prise a l'instant par la camera du Mac, a la demande "
    "de l'utilisateur, pour un assistant vocal. Decris uniquement ce qui est "
    "reellement visible. Distingue ce que tu vois avec certitude de ce qui est "
    "flou ou que tu supposes ; n'invente jamais. Tu peux decrire les personnes "
    "(posture, vetements, expression) mais n'identifie jamais qui elles sont et "
    "ne devine ni leur nom, ni leur age precis, ni d'attribut sensible. Reponds "
    "en francais, en deux ou trois phrases concises."
)
_DESCRIBE_PROMPT = f"{_CAMERA_RULES} Decris la scene : lieu, objets principaux, texte lisible."


class CameraCapability:
    def __init__(self, camera: CameraCapture | None = None,
                 vision_tools: VisionTools | None = None):
        self.camera = camera if camera is not None else CameraCapture()
        self.vision_tools = vision_tools if vision_tools is not None else VisionTools()

    def describe(self, question: str | None = None) -> ToolResult:
        action = "describe_camera"
        prompt = _DESCRIBE_PROMPT
        if isinstance(question, str) and question.strip():
            prompt = (f"{_CAMERA_RULES} Reponds a cette question a partir de la photo : "
                      f"{question.strip()[:300]}")
        try:
            path = self.camera.capture()
        except CameraError as error:
            return ToolResult.failure(action, error.message, error_code=error.code)
        try:
            analysis = self.vision_tools.analyze(str(path), prompt)
        except VisionError as error:
            return ToolResult.failure(action, error.message,
                                      error_code=error.code or "vision_failed")
        except Exception as error:
            return ToolResult.failure(action, f"Echec de l'analyse visuelle : {error}",
                                      error_code="system_error")
        finally:
            Path(path).unlink(missing_ok=True)
        return ToolResult.success(action, analysis["analysis"],
                                  analysis=analysis["analysis"], source="camera",
                                  model=analysis["model"], image_kept=False,
                                  duration_ms=analysis["duration_ms"])

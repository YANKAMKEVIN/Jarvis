from __future__ import annotations

import re
from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.screenshot import ScreenshotCapability
from jarvis.tools.accessibility import normalize_text
from jarvis.tools.vision import VisionError, VisionTools


VALID_TARGETS = {"screen", "window"}

# The model sometimes names the target loosely ("active_window", "l'ecran"...).
# Resolve by keyword rather than exact string so underscores, apostrophes and
# extra words don't cause a spurious invalid_target.
_SCREEN_TOKENS = {"screen", "ecran", "fullscreen", "display"}
_WINDOW_TOKENS = {"window", "fenetre", "app", "application"}

# Reliability-first instructions: Jarvis must separate what it clearly sees from
# what it cannot read and what it would merely infer, and never invent a value
# that is not visible. Read-only: no coordinates, no action suggestions.
_BASE_RULES = (
    "Tu analyses une capture d'ecran macOS pour un assistant vocal. Decris ou "
    "reponds uniquement a partir de ce qui est reellement visible. Distingue "
    "clairement ce que tu lis avec certitude, ce qui est illisible ou flou, et "
    "ce que tu ne fais que supposer. Si une information demandee n'est pas "
    "visible ou lisible, dis-le explicitement, n'invente jamais. Reponds en "
    "francais, de maniere concise et factuelle. Ne donne pas de coordonnees, ne "
    "propose pas d'action ni de clic."
)

_DESCRIBE_PROMPT = (
    f"{_BASE_RULES} Decris ce qui est affiche a l'ecran : application ou page "
    "visible, elements principaux, et le texte lisible important."
)


class VisionCapability:
    """Jarvis's read-only eyes: capture the screen, then analyse the image.

    Strict separation from action: this capability only observes. It reuses the
    verified ScreenshotCapability for capture and a one-shot multimodal call for
    understanding. It never returns coordinates and never triggers any action.
    """

    def __init__(
        self,
        screenshot: ScreenshotCapability | None = None,
        vision_tools: VisionTools | None = None,
    ):
        self.screenshot = screenshot if screenshot is not None else ScreenshotCapability()
        self.vision_tools = vision_tools if vision_tools is not None else VisionTools()

    def describe_screen(
        self,
        target: str = "window",
        app_name: str | None = None,
    ) -> ToolResult:
        return self._capture_and_analyze(
            action="describe_screen",
            prompt=_DESCRIBE_PROMPT,
            target=target,
            app_name=app_name,
            question=None,
        )

    def ask_about_screen(
        self,
        question: str,
        target: str = "window",
        app_name: str | None = None,
    ) -> ToolResult:
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure(
                action="ask_about_screen",
                message="La question sur l'ecran est obligatoire.",
                error_code="invalid_question",
            )

        prompt = (
            f"{_BASE_RULES} Reponds a cette question a partir de la capture : "
            f"{question.strip()}"
        )
        return self._capture_and_analyze(
            action="ask_about_screen",
            prompt=prompt,
            target=target,
            app_name=app_name,
            question=question,
        )

    # -- internals --------------------------------------------------------

    def _capture_and_analyze(
        self,
        action: str,
        prompt: str,
        target: str,
        app_name: str | None,
        question: str | None,
    ) -> ToolResult:
        resolved = self._resolve_target(target)

        if resolved is None:
            return ToolResult.failure(
                action=action,
                message="La cible doit etre 'screen' ou 'window'.",
                error_code="invalid_target",
            )

        target = resolved

        capture = self._capture(target, app_name)

        if not capture.ok:
            return ToolResult.failure(
                action=action,
                message=(
                    "La capture a echoue, aucune analyse n'a ete lancee : "
                    f"{capture.message}"
                ),
                error_code=capture.error_code or "capture_failed",
            )

        if not capture.data.get("state_confirmed"):
            return ToolResult.failure(
                action=action,
                message=(
                    "La capture n'a pas pu etre confirmee ; aucune analyse "
                    "visuelle n'a ete lancee."
                ),
                error_code="capture_not_confirmed",
            )

        image_path = capture.data.get("path")

        try:
            analysis = self.vision_tools.analyze(image_path, prompt)
        except VisionError as error:
            return self._vision_failure(action, error)
        except Exception as error:
            return ToolResult.failure(
                action=action,
                message=f"Echec de l'analyse visuelle : {error}",
                error_code="system_error",
            )

        return ToolResult.success(
            action=action,
            message=analysis["analysis"],
            analysis=analysis["analysis"],
            source=target,
            target_app=capture.data.get("target_app") if target == "window" else None,
            model=analysis["model"],
            question_length=self._safe_len(question),
            image_path=image_path,
            image_bytes=analysis["image_bytes"],
            image_width=capture.data.get("width"),
            image_height=capture.data.get("height"),
            duration_ms=analysis["duration_ms"],
        )

    @staticmethod
    def _resolve_target(target: str) -> str | None:
        if target in VALID_TARGETS:
            return target

        if not isinstance(target, str):
            return None

        tokens = set(re.sub(r"[^a-z0-9]+", " ", normalize_text(target)).split())

        if tokens & _SCREEN_TOKENS:
            return "screen"

        if tokens & _WINDOW_TOKENS:
            return "window"

        return None

    def _capture(self, target: str, app_name: str | None) -> ToolResult:
        if target == "screen":
            return self.screenshot.capture_screen()

        return self.screenshot.capture_window(app_name)

    @staticmethod
    def _vision_failure(action: str, error: VisionError) -> ToolResult:
        return ToolResult(
            ok=False,
            action=action,
            message=error.message,
            data=dict(error.data),
            error_code=error.code or "vision_error",
        )

    @staticmethod
    def _safe_len(value: str | None) -> int | None:
        return len(value) if isinstance(value, str) else None

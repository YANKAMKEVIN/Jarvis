"""Transform the clipboard text with the local model: rewrite, fix, translate.

Reads what the user copied, applies a natural-language instruction via the
free planner model (Ollama/Gemini), and writes the result back to the clipboard
for the user to paste. No GUI automation, so it is reliable. The transformed
text is not returned to the voice model (it can be long or private): only its
length, so Jarvis just says it is ready in the clipboard.
"""

from __future__ import annotations

from jarvis.capabilities.results import ToolResult


_SYSTEM = (
    "Tu transformes le texte fourni selon l'instruction de l'utilisateur "
    "(reformuler, corriger, traduire, resumer, changer le ton...). Rends "
    "UNIQUEMENT le texte transforme, sans explication, sans guillemets autour, "
    "sans prefixe ni suffixe. Conserve la langue demandee par l'instruction, "
    "sinon la langue d'origine."
)


class TextWorkshopCapability:
    def __init__(self, clipboard, model=None):
        self.clipboard = clipboard
        self._model = model

    def _get_model(self):
        if self._model is None:
            from jarvis.planner.models import build_planner_model

            self._model = build_planner_model()
        return self._model

    def rewrite_clipboard(self, instruction: str) -> ToolResult:
        if not isinstance(instruction, str) or not instruction.strip():
            return ToolResult.failure(
                action="rewrite_clipboard",
                message="Dis ce que tu veux faire du texte (reformuler, corriger, traduire...).",
                error_code="invalid_instruction",
            )

        got = self.clipboard.get_clipboard_text()
        if not got.ok:
            return got
        if not got.data.get("has_text"):
            return ToolResult.failure(
                action="rewrite_clipboard",
                message="Le presse-papiers ne contient pas de texte a transformer.",
                error_code="empty_clipboard",
            )
        if got.data.get("truncated"):
            # Rewriting only the visible start would drop the rest on paste.
            return ToolResult.failure(
                action="rewrite_clipboard",
                message="Le texte copie est trop long pour etre transforme en une fois.",
                error_code="clipboard_too_long",
            )

        text = got.data.get("text") or ""
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Instruction : {instruction.strip()}\n\nTexte :\n{text}"},
        ]
        try:
            turn = self._get_model().complete(messages, [])
        except Exception as error:
            return ToolResult.failure(
                action="rewrite_clipboard",
                message=f"La transformation du texte a echoue : {error}",
                error_code="model_error",
            )

        transformed = (turn.text or "").strip()
        if not transformed:
            return ToolResult.failure(
                action="rewrite_clipboard",
                message="Le modele n'a pas renvoye de texte transforme.",
                error_code="empty_result",
            )

        written = self.clipboard.set_clipboard_text(transformed)
        if not written.ok:
            return written

        return ToolResult.success(
            action="rewrite_clipboard",
            message="Texte transforme et copie dans le presse-papiers ; tu peux le coller.",
            transformed_length=len(transformed),
            state_confirmed=written.data.get("state_confirmed"),
        )

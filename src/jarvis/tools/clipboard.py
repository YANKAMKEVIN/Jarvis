from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Callable


MAX_RETURN_CHARS = 4000


class ClipboardError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class ClipboardTools:
    pbpaste_path: str = "/usr/bin/pbpaste"
    pbcopy_path: str = "/usr/bin/pbcopy"
    max_return_chars: int = MAX_RETURN_CHARS
    runner: Runner = subprocess.run

    def get_text(self) -> dict[str, Any]:
        text = self._read_raw_text()
        return self._text_state(text)

    def set_text(self, text: str) -> dict[str, Any]:
        text = self._validate_text(text)
        self._write_raw_text(text)
        observed = self._read_raw_text_after_command()
        state_confirmed = observed == text and not observed.verification_data

        return {
            "command_executed": True,
            "state_confirmed": state_confirmed,
            "length": len(text),
            "has_text": bool(text),
            "content_type": "text" if text else "no_text_detected",
            **observed.verification_data,
        }

    def clear(self) -> dict[str, Any]:
        self._write_raw_text("")
        observed = self._read_raw_text_after_command()
        state_confirmed = observed == "" and not observed.verification_data

        return {
            "command_executed": True,
            "state_confirmed": state_confirmed,
            "has_text": False if state_confirmed else bool(observed),
            "length": 0 if state_confirmed else len(observed),
            "content_type": (
                "no_text_detected"
                if state_confirmed
                else "text"
            ),
            **observed.verification_data,
        }

    def _read_raw_text(self) -> str:
        try:
            completed = self.runner(
                [self.pbpaste_path, "-Prefer", "txt"],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ClipboardError(
                "La commande pbpaste est indisponible.",
                "pbpaste_missing",
            ) from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ClipboardError(
                detail or "La lecture du presse-papiers a echoue.",
                "clipboard_read_error",
            )

        return completed.stdout

    def _read_raw_text_after_command(self) -> "_ObservedClipboardText":
        try:
            return _ObservedClipboardText(self._read_raw_text())
        except ClipboardError as error:
            return _ObservedClipboardText(
                "",
                {
                    "verification_error_code": error.code,
                    "verification_error": error.message,
                },
            )

    def _write_raw_text(self, text: str) -> None:
        try:
            completed = self.runner(
                [self.pbcopy_path],
                input=text,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ClipboardError(
                "La commande pbcopy est indisponible.",
                "pbcopy_missing",
            ) from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise ClipboardError(
                detail or "L'ecriture du presse-papiers a echoue.",
                "clipboard_write_error",
            )

    def _text_state(self, text: str) -> dict[str, Any]:
        if text == "":
            return {
                "has_text": False,
                "text": None,
                "length": 0,
                "returned_length": 0,
                "truncated": False,
                "content_type": "no_text_detected",
            }

        returned = text[: self.max_return_chars]

        return {
            "has_text": True,
            "text": returned,
            "length": len(text),
            "returned_length": len(returned),
            "truncated": len(text) > self.max_return_chars,
            "content_type": "text",
        }

    @staticmethod
    def _validate_text(text: str) -> str:
        if not isinstance(text, str):
            raise ClipboardError(
                "Le texte a copier doit etre une chaine de caracteres.",
                "invalid_clipboard_text",
            )

        return text


class _ObservedClipboardText(str):
    def __new__(cls, value: str, verification_data: dict[str, Any] | None = None):
        instance = super().__new__(cls, value)
        instance.verification_data = verification_data or {}
        return instance

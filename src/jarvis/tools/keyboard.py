from __future__ import annotations

import subprocess
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable


MAX_TYPE_TEXT_CHARS = 1000

SAFE_KEYS = {
    "enter",
    "escape",
    "tab",
    "space",
    "arrow_up",
    "arrow_down",
    "arrow_left",
    "arrow_right",
}

SAFE_HOTKEYS = {
    ("command", "a"),
    ("command", "c"),
    ("command", "v"),
    ("command", "z"),
    ("command", "shift", "z"),
    ("command", "f"),
    ("command", "s"),
}

MODIFIERS = ("command", "control", "option", "shift")

KEY_CODES = {
    "enter": 36,
    "escape": 53,
    "tab": 48,
    "space": 49,
    "arrow_up": 126,
    "arrow_down": 125,
    "arrow_left": 123,
    "arrow_right": 124,
    # backspace is intentionally absent from SAFE_KEYS, so it is never reachable
    # through the generic press_key/validate_key path. Its key code lives here
    # only for the restricted delete_backward primitive below.
    "backspace": 51,
}

KEY_ALIASES = {
    "enter": "enter",
    "return": "enter",
    "retour": "enter",
    "entree": "enter",
    "escape": "escape",
    "esc": "escape",
    "echap": "escape",
    "tab": "tab",
    "tabulation": "tab",
    "space": "space",
    "espace": "space",
    "arrowup": "arrow_up",
    "arrow_up": "arrow_up",
    "up": "arrow_up",
    "haut": "arrow_up",
    "fleche_haut": "arrow_up",
    "arrowdown": "arrow_down",
    "arrow_down": "arrow_down",
    "down": "arrow_down",
    "bas": "arrow_down",
    "fleche_bas": "arrow_down",
    "arrowleft": "arrow_left",
    "arrow_left": "arrow_left",
    "left": "arrow_left",
    "gauche": "arrow_left",
    "fleche_gauche": "arrow_left",
    "arrowright": "arrow_right",
    "arrow_right": "arrow_right",
    "right": "arrow_right",
    "droite": "arrow_right",
    "fleche_droite": "arrow_right",
}

HOTKEY_KEY_ALIASES = {
    **KEY_ALIASES,
    "a": "a",
    "c": "c",
    "v": "v",
    "z": "z",
    "f": "f",
    "s": "s",
    "q": "q",
    "w": "w",
    "delete": "delete",
    "del": "delete",
    "backspace": "backspace",
    "suppr": "delete",
}

MODIFIER_ALIASES = {
    "cmd": "command",
    "commande": "command",
    "command": "command",
    "ctrl": "control",
    "control": "control",
    "option": "option",
    "alt": "option",
    "shift": "shift",
    "maj": "shift",
}


class KeyboardError(Exception):
    def __init__(
        self,
        message: str,
        code: str,
        data: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.data = data or {}


Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass
class KeyboardTools:
    osascript_path: str = "/usr/bin/osascript"
    max_text_chars: int = MAX_TYPE_TEXT_CHARS
    runner: Runner = subprocess.run

    def validate_type_text(self, text: str) -> dict[str, Any]:
        if not isinstance(text, str):
            raise KeyboardError(
                "Le texte a saisir doit etre une chaine de caracteres.",
                "invalid_text",
            )

        if text == "":
            raise KeyboardError(
                "Le texte a saisir ne peut pas etre vide.",
                "empty_text",
            )

        if len(text) > self.max_text_chars:
            raise KeyboardError(
                (
                    "Le texte a saisir est trop long pour KeyboardCapability V1 "
                    f"({self.max_text_chars} caracteres maximum)."
                ),
                "text_too_long",
                {"max_length": self.max_text_chars, "length": len(text)},
            )

        normalized = text.replace("\r\n", "\n").replace("\r", "\n")

        return {
            "text": normalized,
            "length": len(normalized),
            "line_count": normalized.count("\n") + 1,
        }

    def validate_key(self, key: str) -> str:
        normalized = self._normalize_key_name(key)

        if normalized not in SAFE_KEYS:
            code = (
                "keyboard_key_not_allowed"
                if normalized in {"delete", "backspace"}
                else "unknown_key"
            )
            raise KeyboardError(
                "Cette touche n'est pas autorisee en V1.",
                code,
                {"key": normalized},
            )

        return normalized

    def validate_hotkey(self, keys: list[str]) -> tuple[str, ...]:
        if not isinstance(keys, list):
            raise KeyboardError(
                "Un raccourci clavier doit contenir au moins un modificateur et une touche.",
                "invalid_hotkey",
            )

        keys = self._expand_hotkey_items(keys)

        if len(keys) < 2:
            raise KeyboardError(
                "Un raccourci clavier doit contenir au moins un modificateur et une touche.",
                "invalid_hotkey",
            )

        modifiers = []
        main_keys = []

        for item in keys:
            normalized = self._normalize_token(item)

            if normalized in MODIFIER_ALIASES:
                modifier = MODIFIER_ALIASES[normalized]

                if modifier in modifiers:
                    raise KeyboardError(
                        "Un modificateur est present plusieurs fois.",
                        "duplicate_modifier",
                        {"modifier": modifier},
                    )

                modifiers.append(modifier)
                continue

            if normalized in HOTKEY_KEY_ALIASES:
                main_keys.append(HOTKEY_KEY_ALIASES[normalized])
                continue

            raise KeyboardError(
                "Modificateur ou touche inconnu.",
                "unknown_modifier_or_key",
                {"key": normalized},
            )

        if len(main_keys) != 1 or not modifiers:
            raise KeyboardError(
                "Un raccourci clavier doit contenir une seule touche principale.",
                "invalid_hotkey",
            )

        ordered_modifiers = [
            modifier
            for modifier in MODIFIERS
            if modifier in modifiers
        ]
        normalized_hotkey = tuple(ordered_modifiers + [main_keys[0]])

        if normalized_hotkey not in SAFE_HOTKEYS:
            raise KeyboardError(
                "Ce raccourci clavier n'est pas autorise en V1.",
                "hotkey_not_allowed",
                {"keys": list(normalized_hotkey)},
            )

        return normalized_hotkey

    @staticmethod
    def _expand_hotkey_items(keys: list[str]) -> list[str]:
        expanded = []

        for item in keys:
            if not isinstance(item, str):
                raise KeyboardError(
                    "Les touches doivent etre des chaines de caracteres.",
                    "invalid_key",
                )

            parts = [
                part
                for part in item.replace("＋", "+").split("+")
                if part.strip()
            ]

            if not parts:
                raise KeyboardError(
                    "Un raccourci clavier contient une touche vide.",
                    "invalid_hotkey",
                )

            expanded.extend(parts)

        return expanded

    def type_text(self, text: str) -> dict[str, Any]:
        validated = self.validate_type_text(text)
        target = self._read_frontmost_context()
        script = self._type_text_script(validated["text"])
        self._run_osascript(script)

        return {
            "command_executed": True,
            "state_confirmed": False,
            "length": validated["length"],
            "line_count": validated["line_count"],
            **target,
        }

    def press_key(self, key: str) -> dict[str, Any]:
        normalized = self.validate_key(key)
        target = self._read_frontmost_context()
        self._run_osascript(self._press_key_script(normalized))

        return {
            "command_executed": True,
            "state_confirmed": False,
            "key": normalized,
            **target,
        }

    def delete_backward(self) -> dict[str, Any]:
        """Send a single Backspace, bypassing the SAFE_KEYS allowlist.

        Restricted primitive for the controlled select-all-and-delete workflow
        only. Backspace stays out of SAFE_KEYS so it is never exposed through the
        generic press_key tool; this method is the single, narrow door to it.
        """
        target = self._read_frontmost_context()
        self._run_osascript(self._press_key_script("backspace"))

        return {
            "command_executed": True,
            "state_confirmed": False,
            "key": "backspace",
            **target,
        }

    def hotkey(self, keys: list[str]) -> dict[str, Any]:
        normalized = self.validate_hotkey(keys)
        target = self._read_frontmost_context()
        self._run_osascript(self._hotkey_script(normalized))

        return {
            "command_executed": True,
            "state_confirmed": False,
            "keys": list(normalized),
            **target,
        }

    def _read_frontmost_context(self) -> dict[str, Any]:
        script = "\n".join([
            'tell application "System Events"',
            "set target_process to first application process whose frontmost is true",
            "set app_name to name of target_process as text",
            'set window_title to ""',
            "try",
            "if exists window 1 of target_process then set window_title to name of window 1 of target_process as text",
            "end try",
            "return app_name & linefeed & window_title",
            "end tell",
        ])

        try:
            output = self._run_osascript(script).stdout.splitlines()
        except KeyboardError as error:
            return {
                "target_app": None,
                "target_window": None,
                "target_context_error_code": error.code,
            }

        return {
            "target_app": output[0].strip() if output else None,
            "target_window": output[1].strip() if len(output) > 1 and output[1].strip() else None,
        }

    def _type_text_script(self, text: str) -> str:
        lines = ['tell application "System Events"']
        segments = text.split("\n")

        for index, segment in enumerate(segments):
            if segment:
                lines.append(f"keystroke {self._applescript_string(segment)}")

            if index < len(segments) - 1:
                lines.append("key code 36")

        lines.append("end tell")
        return "\n".join(lines)

    def _press_key_script(self, key: str) -> str:
        return "\n".join([
            'tell application "System Events"',
            f"key code {KEY_CODES[key]}",
            "end tell",
        ])

    def _hotkey_script(self, keys: tuple[str, ...]) -> str:
        modifiers = keys[:-1]
        key = keys[-1]
        modifier_text = ", ".join(f"{modifier} down" for modifier in modifiers)
        return "\n".join([
            'tell application "System Events"',
            f"keystroke {self._applescript_string(key)} using {{{modifier_text}}}",
            "end tell",
        ])

    def _run_osascript(self, script: str) -> subprocess.CompletedProcess[str]:
        try:
            completed = self.runner(
                [self.osascript_path, "-e", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except FileNotFoundError as error:
            raise KeyboardError(
                "La commande osascript est indisponible.",
                "osascript_missing",
            ) from error
        except subprocess.TimeoutExpired as error:
            raise KeyboardError(
                "La commande clavier macOS a expire.",
                "keyboard_timeout",
            ) from error

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise KeyboardError(
                detail or "La commande clavier macOS a echoue.",
                self._error_code_from_output(detail),
            )

        return completed

    @staticmethod
    def _normalize_token(value: str) -> str:
        if not isinstance(value, str):
            raise KeyboardError(
                "Les touches doivent etre des chaines de caracteres.",
                "invalid_key",
            )

        value = value.strip().lower()
        value = unicodedata.normalize("NFD", value)
        value = "".join(char for char in value if unicodedata.category(char) != "Mn")
        value = value.replace("-", "_").replace(" ", "_")
        return value

    @classmethod
    def _normalize_key_name(cls, key: str) -> str:
        normalized = cls._normalize_token(key)
        normalized = KEY_ALIASES.get(normalized, normalized)

        if normalized in {"delete", "del", "suppr"}:
            return "delete"

        if normalized in {"backspace", "retour_arriere"}:
            return "backspace"

        return normalized

    @staticmethod
    def _applescript_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    @staticmethod
    def _error_code_from_output(output: str) -> str:
        normalized = output.lower()

        if any(
            fragment in normalized
            for fragment in (
                "not authorized",
                "not permitted",
                "not allowed",
                "assistive",
                "accessibility",
                "automation",
            )
        ):
            return "accessibility_permission_error"

        return "system_error"

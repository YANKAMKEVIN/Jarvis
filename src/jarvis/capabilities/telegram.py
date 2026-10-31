from __future__ import annotations

from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.tools.accessibility import normalize_text
from jarvis.tools.telegram_api import (
    DEFAULT_DIALOG_LIMIT,
    SELF_PEER,
    TelegramApiError,
    TelethonBackend,
)


MIN_RECIPIENT_LENGTH = 2

# Spoken names of the user's own "Saved Messages" chat (normalized).
SELF_ALIASES = frozenset({
    "messages enregistres",
    "saved messages",
    "moi",
    "moi meme",
    "moi-meme",
})


class TelegramMessaging:
    """Recipient resolution and sending over the Telegram API, refusing in doubt.

    The recipient is resolved against the user's own recent conversations only
    (never Telegram's global search), and must match exactly ONE of them:
    the full display name, or its leading words ("Joel" for "Joel Chinda"), or
    an @username. Zero or several matches is a refusal. The resolution is
    redone right before sending, so a send never reuses a stale lookup. A send
    is state_confirmed only when Telegram returns the new message's id.
    """

    def __init__(self, backend=None, dialog_limit: int = DEFAULT_DIALOG_LIMIT):
        self.backend = backend if backend is not None else TelethonBackend()
        self.dialog_limit = dialog_limit

    def resolve(self, expected_recipient: str) -> ToolResult:
        """Verify that exactly one conversation matches; never sends."""
        return self._resolve(expected_recipient)[0]

    def _resolve(self, expected_recipient: str) -> tuple[ToolResult, Any]:
        """(result, peer); peer is None unless the result is a verified match."""
        if not isinstance(expected_recipient, str) or not expected_recipient.strip():
            return ToolResult.failure(
                action="verify_recipient",
                message="Le destinataire attendu est obligatoire.",
                error_code="invalid_recipient",
            ), None

        needle = normalize_text(expected_recipient)
        if len(needle.lstrip("@")) < MIN_RECIPIENT_LENGTH:
            return ToolResult.failure(
                action="verify_recipient",
                message="Le destinataire attendu est trop court pour etre verifie.",
                error_code="invalid_recipient",
            ), None

        if needle in SELF_ALIASES:
            return self._verified("self", expected_recipient), SELF_PEER

        try:
            dialogs = self.backend.list_dialogs(limit=self.dialog_limit)
        except TelegramApiError as error:
            return ToolResult.failure(
                action="verify_recipient",
                message=f"{error.message} Rien n'a ete prepare.",
                error_code=error.code,
            ), None

        matches = self._matches(needle, dialogs)
        if len(matches) == 1:
            match = matches[0]
            peer = SELF_PEER if match.get("is_self") else match["id"]
            return self._verified(match.get("kind"), expected_recipient), peer

        reason = "recipient_not_found" if not matches else "recipient_ambiguous"
        message = (
            "Aucune conversation Telegram ne correspond a ce destinataire. "
            "Donne le nom exact du contact ; rien n'a ete prepare."
            if not matches else
            f"{len(matches)} conversations Telegram correspondent a ce nom. "
            "Donne le nom complet du contact ; rien n'a ete prepare."
        )
        return ToolResult(
            ok=False,
            action="verify_recipient",
            message=message,
            data={
                "recipient_verified": False,
                "reason": reason,
                "match_count": len(matches),
                "target_app": "Telegram",
            },
            error_code="recipient_not_verified",
        ), None

    def send(self, expected_recipient: str, text: str) -> ToolResult:
        if not isinstance(text, str) or not text.strip():
            return ToolResult.failure(
                action="send_text",
                message="Le message a envoyer est vide.",
                error_code="invalid_text",
            )

        # Re-resolve now: the chat list may have changed since the preparation.
        resolved, peer = self._resolve(expected_recipient)
        if not resolved.ok:
            return resolved

        try:
            message_id = self.backend.send_message(peer, text)
        except TelegramApiError as error:
            if error.may_have_sent:
                return ToolResult(
                    ok=False,
                    action="send_text",
                    message=(
                        "Envoi Telegram incertain : verifie la conversation avant "
                        "toute nouvelle tentative."
                    ),
                    data={"command_executed": True, "state_confirmed": False},
                    error_code=error.code,
                )
            return ToolResult.failure(
                action="send_text",
                message=f"{error.message} Rien n'a ete envoye.",
                error_code=error.code,
            )

        return ToolResult.success(
            action="send_text",
            message="Message envoye : Telegram a confirme sa reception.",
            command_executed=True,
            state_confirmed=True,
            app="Telegram",
            text_length=len(text),
            message_id=message_id,
        )

    @staticmethod
    def _matches(needle: str, dialogs: Any) -> list[dict[str, Any]]:
        if not isinstance(dialogs, list):
            return []
        # Broadcast channels are never targets: posting there is public.
        dialogs = [
            d for d in dialogs
            if isinstance(d, dict) and "id" in d and d.get("kind") != "channel"
        ]

        if needle.startswith("@"):
            handle = needle[1:]
            return [
                d for d in dialogs
                if isinstance(d.get("username"), str)
                and d["username"].casefold() == handle
            ]

        exact = [d for d in dialogs if normalize_text(d.get("name")) == needle]
        if exact:
            return _unique(exact)

        words = needle.split()
        leading = [
            d for d in dialogs
            if normalize_text(d.get("name")).split()[: len(words)] == words
        ]
        return _unique(leading)

    @staticmethod
    def _verified(kind: Any, expected_recipient: str) -> ToolResult:
        return ToolResult.success(
            action="verify_recipient",
            message="Le destinataire Telegram a ete verifie (une seule conversation correspond).",
            recipient_verified=True,
            target_app="Telegram",
            recipient_kind=kind,
            recipient_length=len(expected_recipient),
        )


def _unique(dialogs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[Any, dict[str, Any]] = {}
    for dialog in dialogs:
        seen.setdefault(dialog["id"], dialog)
    return list(seen.values())

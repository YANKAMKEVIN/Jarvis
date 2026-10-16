"""Apple Mail: read unread messages and create drafts (local, AppleScript)."""

from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.tools.mail import MailError, MailTools


class MailCapability:
    def __init__(self, mail_tools: MailTools | None = None):
        self.mail_tools = mail_tools if mail_tools is not None else MailTools()

    def list_unread(self, limit: int = 10) -> ToolResult:
        try:
            state = self.mail_tools.list_unread(limit)
        except MailError as error:
            return self._failure("list_unread_emails", error)
        except Exception as error:
            return self._system_error("list_unread_emails", error)

        count = state.get("unread_count", 0)
        message = (
            f"{count} mail(s) non lu(s) dans la boite de reception."
            if count
            else "Aucun mail non lu dans la boite de reception."
        )
        return ToolResult.success(action="list_unread_emails", message=message, **state)

    def create_draft(self, recipient: str, subject: str, body: str) -> ToolResult:
        if not isinstance(recipient, str) or not recipient.strip():
            return ToolResult.failure(
                action="draft_email",
                message="Le destinataire du brouillon est obligatoire.",
                error_code="invalid_recipient",
            )
        if not isinstance(body, str) or not body.strip():
            return ToolResult.failure(
                action="draft_email",
                message="Le corps du brouillon est obligatoire.",
                error_code="invalid_body",
            )
        subject = subject if isinstance(subject, str) else ""
        try:
            state = self.mail_tools.create_draft(recipient.strip(), subject.strip(), body)
        except MailError as error:
            return self._failure("draft_email", error)
        except Exception as error:
            return self._system_error("draft_email", error)

        return ToolResult.success(
            action="draft_email",
            message=f"Brouillon prepare pour {recipient.strip()} (non envoye).",
            **state,
        )

    @staticmethod
    def _failure(action: str, error: MailError) -> ToolResult:
        return ToolResult.failure(
            action=action, message=error.message, error_code=error.code or "mail_error",
        )

    @staticmethod
    def _system_error(action: str, error: Exception) -> ToolResult:
        return ToolResult.failure(
            action=action, message=f"Echec de la messagerie : {error}", error_code="system_error",
        )

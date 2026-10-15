from __future__ import annotations

from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
from jarvis.capabilities.windows import WindowCapability
from jarvis.tools.accessibility import normalize_text


# Label fields checked on the conversation header element. AXValue is never
# read. Message bubbles are never scanned, so a name that merely appears inside
# a message cannot be mistaken for the open conversation's recipient.
_HEADER_LABEL_FIELDS = ("description", "title")
MIN_RECIPIENT_LENGTH = 2

# Accessibility identifiers of the "who am I talking to" header, per messaging
# app. Extensible: add an app's header id here rather than branching on the app
# name. WhatsApp exposes the open conversation's recipient as the description of
# NavigationBar_HeaderViewButton.
DEFAULT_CONVERSATION_HEADER_IDENTIFIERS = (
    "NavigationBar_HeaderViewButton",
)

# Accessibility query that focuses the message composer, per app. The value is
# an AX identifier (matched by focus_ui_element), which is stable and
# locale-independent, unlike the visible placeholder text. Extensible per app.
DEFAULT_COMPOSER_QUERIES = {
    "whatsapp": "ChatBar_ComposerTextView",
}


class MessagingCapability:
    """Safety checks for sending messages to people, on top of confirmation.

    The main risk of sending a message is reaching the wrong recipient, not the
    typing. verify_recipient confirms that the conversation currently in front
    belongs to the intended app and visibly names the intended recipient; it
    fails safe (refuses) when it cannot prove this, so the send is never
    prepared against the wrong chat. It never reads message content (AXValue).
    """

    def __init__(
        self,
        windows: WindowCapability | None = None,
        ui_accessibility: UIAccessibilityCapability | None = None,
        header_identifiers: tuple[str, ...] | None = None,
        composer_queries: dict[str, str] | None = None,
    ):
        self.windows = windows if windows is not None else WindowCapability()
        self.ui_accessibility = (
            ui_accessibility
            if ui_accessibility is not None
            else UIAccessibilityCapability()
        )
        self.header_identifiers = (
            tuple(header_identifiers)
            if header_identifiers is not None
            else DEFAULT_CONVERSATION_HEADER_IDENTIFIERS
        )
        source = (
            composer_queries
            if composer_queries is not None
            else DEFAULT_COMPOSER_QUERIES
        )
        self._composer_queries = {
            key.casefold(): value for key, value in source.items()
        }

    def composer_query(self, app_name: str) -> str | None:
        """AX query that focuses the composer of a known messaging app."""
        if not isinstance(app_name, str):
            return None

        return self._composer_queries.get(app_name.strip().casefold())

    def verify_recipient(self, app_name: str, expected_recipient: str) -> ToolResult:
        if not isinstance(app_name, str) or not app_name.strip():
            return ToolResult.failure(
                action="verify_recipient",
                message="Le nom de l'application de messagerie est obligatoire.",
                error_code="invalid_app_name",
            )

        if not isinstance(expected_recipient, str) or not expected_recipient.strip():
            return ToolResult.failure(
                action="verify_recipient",
                message="Le destinataire attendu est obligatoire.",
                error_code="invalid_recipient",
            )

        needle = normalize_text(expected_recipient)

        if len(needle) < MIN_RECIPIENT_LENGTH:
            return ToolResult.failure(
                action="verify_recipient",
                message="Le destinataire attendu est trop court pour etre verifie.",
                error_code="invalid_recipient",
            )

        active = self.windows.get_active_window()

        if not active.ok:
            return ToolResult.failure(
                action="verify_recipient",
                message=(
                    "Impossible de lire la fenetre active pour verifier le "
                    "destinataire ; aucun envoi n'a ete prepare."
                ),
                error_code=active.error_code or "no_window",
            )

        observed_app = active.data.get("target_app")

        if not self._same_app(app_name, observed_app):
            return ToolResult(
                ok=False,
                action="verify_recipient",
                message=(
                    f"{app_name} n'est pas l'application active. Ouvre la "
                    "conversation voulue avant l'envoi."
                ),
                data={
                    "recipient_verified": False,
                    "reason": "active_app_mismatch",
                    "observed_app": observed_app,
                },
                error_code="recipient_not_verified",
            )

        inspected = self.ui_accessibility.inspect_ui(max_depth=6, max_elements=150)

        if not inspected.ok:
            return ToolResult.failure(
                action="verify_recipient",
                message=(
                    "Impossible d'inspecter la fenetre pour verifier le "
                    "destinataire ; aucun envoi n'a ete prepare."
                ),
                error_code=inspected.error_code or "inspect_failed",
            )

        headers = self._header_elements(inspected.data.get("elements", []))

        if not headers:
            return ToolResult(
                ok=False,
                action="verify_recipient",
                message=(
                    "Impossible de localiser l'en-tete de la conversation pour "
                    "verifier le destinataire ; rien n'a ete prepare."
                ),
                data={
                    "recipient_verified": False,
                    "reason": "conversation_header_not_found",
                    "target_app": observed_app,
                },
                error_code="recipient_not_verified",
            )

        if not self._header_matches(needle, headers):
            return ToolResult(
                ok=False,
                action="verify_recipient",
                message=(
                    "La conversation ouverte ne correspond pas au destinataire "
                    "attendu. Ouvre la bonne conversation ; rien n'a ete prepare."
                ),
                data={
                    "recipient_verified": False,
                    "reason": "header_mismatch",
                    "target_app": observed_app,
                },
                error_code="recipient_not_verified",
            )

        return ToolResult.success(
            action="verify_recipient",
            message="Le destinataire de la conversation ouverte a ete verifie.",
            recipient_verified=True,
            target_app=observed_app,
            recipient_length=len(expected_recipient),
        )

    def _header_elements(self, elements: Any) -> list[dict[str, Any]]:
        if not isinstance(elements, list):
            return []

        return [
            element
            for element in elements
            if isinstance(element, dict)
            and element.get("identifier") in self.header_identifiers
        ]

    @staticmethod
    def _header_matches(needle: str, headers: list[dict[str, Any]]) -> bool:
        for header in headers:
            for field in _HEADER_LABEL_FIELDS:
                value = header.get(field)

                if isinstance(value, str) and needle in normalize_text(value):
                    return True

        return False

    @staticmethod
    def _same_app(expected: str, observed: Any) -> bool:
        if not isinstance(expected, str) or not isinstance(observed, str):
            return False

        return expected.strip().casefold() == observed.strip().casefold()

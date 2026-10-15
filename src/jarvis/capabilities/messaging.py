from __future__ import annotations

import time
from typing import Any

from jarvis.capabilities.apps import AppCapability
from jarvis.capabilities.keyboard import KeyboardCapability
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

# AX query that focuses the contact/conversation search field, per app. Used to
# navigate to a recipient by name before sending.
DEFAULT_SEARCH_QUERIES = {
    "whatsapp": "TokenizedSearchBar_TextView",
}

# Reasons from verify_recipient that navigation can try to resolve (wrong chat
# open, or the app not frontmost). Anything else is a hard refusal.
_NAVIGABLE_REASONS = {
    "header_mismatch",
    "conversation_header_not_found",
    "active_app_mismatch",
}


class MessagingCapability:
    """Safety checks for sending messages to people, on top of confirmation.

    The main risk of sending a message is reaching the wrong recipient, not the
    typing. verify_recipient confirms that the conversation currently in front
    belongs to the intended app and visibly names the intended recipient; it
    fails safe (refuses) when it cannot prove this, so the send is never
    prepared against the wrong chat. It never reads message content (AXValue).
    """

    DEFAULT_SEARCH_SETTLE_SECONDS = 0.4

    def __init__(
        self,
        windows: WindowCapability | None = None,
        ui_accessibility: UIAccessibilityCapability | None = None,
        apps: AppCapability | None = None,
        keyboard: KeyboardCapability | None = None,
        header_identifiers: tuple[str, ...] | None = None,
        composer_queries: dict[str, str] | None = None,
        search_queries: dict[str, str] | None = None,
        search_settle_seconds: float = DEFAULT_SEARCH_SETTLE_SECONDS,
        sleeper=None,
    ):
        self.windows = windows if windows is not None else WindowCapability()
        self.ui_accessibility = (
            ui_accessibility
            if ui_accessibility is not None
            else UIAccessibilityCapability()
        )
        self.apps = apps if apps is not None else AppCapability()
        self.keyboard = keyboard if keyboard is not None else KeyboardCapability()
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
        search_source = (
            search_queries
            if search_queries is not None
            else DEFAULT_SEARCH_QUERIES
        )
        self._search_queries = {
            key.casefold(): value for key, value in search_source.items()
        }
        self.search_settle_seconds = max(0.0, float(search_settle_seconds))
        self.sleeper = sleeper if sleeper is not None else time.sleep

    def search_query(self, app_name: str) -> str | None:
        if not isinstance(app_name, str):
            return None

        return self._search_queries.get(app_name.strip().casefold())

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

    def ensure_recipient(self, app_name: str, expected_recipient: str) -> ToolResult:
        """Guarantee the intended recipient's chat is open, navigating if needed.

        Verifies the open conversation; if it is the wrong chat (or the app is
        not frontmost) and the app supports contact search, navigates to the
        recipient and verifies again. Returns a verified result, or a fail-safe
        refusal — the send is only prepared when this returns ok.
        """
        verification = self.verify_recipient(app_name, expected_recipient)

        if verification.ok:
            return verification

        resolvable = (
            verification.error_code == "recipient_not_verified"
            and verification.data.get("reason") in _NAVIGABLE_REASONS
            and self.search_query(app_name) is not None
        )

        if not resolvable:
            return verification

        navigation = self.navigate_to_recipient(app_name, expected_recipient)

        if not navigation.ok:
            return navigation

        # Re-verify against the header AFTER navigating: this is the safety net.
        # If navigation opened the wrong chat (or none), this refuses and nothing
        # is ever sent to the wrong person.
        return self.verify_recipient(app_name, expected_recipient)

    def navigate_to_recipient(self, app_name: str, expected_recipient: str) -> ToolResult:
        """Open the app, search the recipient by name and open the top result.

        Mechanical only (focus search, type, Enter); correctness is confirmed by
        the caller's re-verification of the conversation header. Non-destructive:
        it never sends anything.
        """
        query = self.search_query(app_name)

        if query is None:
            return ToolResult.failure(
                action="navigate_to_recipient",
                message="La recherche de contact n'est pas supportee pour cette application.",
                error_code="search_not_supported",
            )

        opened = self.apps.open_app(app_name)

        if not opened.ok:
            return ToolResult.failure(
                action="navigate_to_recipient",
                message=f"Impossible d'ouvrir {app_name}.",
                error_code=opened.error_code or "system_error",
            )

        focused = self.windows.focus_window(app_name)

        if not focused.ok or focused.data.get("state_confirmed") is not True:
            return ToolResult.failure(
                action="navigate_to_recipient",
                message=f"Impossible de mettre {app_name} au premier plan.",
                error_code=focused.error_code or "no_window",
            )

        search = self.ui_accessibility.focus_ui_element(query)

        if not search.ok or search.data.get("state_confirmed") is not True:
            return ToolResult.failure(
                action="navigate_to_recipient",
                message="Le champ de recherche n'a pas pu etre focalise.",
                error_code=search.error_code or "search_field_not_found",
            )

        typed = self.keyboard.type_text(expected_recipient)

        if typed.data.get("command_executed") is not True:
            return ToolResult.failure(
                action="navigate_to_recipient",
                message="La saisie du nom dans la recherche a echoue.",
                error_code=typed.error_code or "command_not_executed",
            )

        self.sleeper(self.search_settle_seconds)

        entered = self.keyboard.press_key("enter")

        if entered.data.get("command_executed") is not True:
            return ToolResult.failure(
                action="navigate_to_recipient",
                message="L'ouverture du resultat de recherche a echoue.",
                error_code=entered.error_code or "command_not_executed",
            )

        self.sleeper(self.search_settle_seconds)

        return ToolResult.success(
            action="navigate_to_recipient",
            message="Navigation vers le contact envoyee ; verification en cours.",
            target_app=app_name,
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

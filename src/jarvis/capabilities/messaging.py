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

# AX identifier of the "send" button, per app. Pressing it is more reliable than
# a Return keystroke and needs no composer focus (which some apps, e.g. the
# WhatsApp Catalyst app, never confirm).
DEFAULT_SEND_BUTTON_QUERIES = {
    "whatsapp": "ChatBar_SendButton",
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
    # Bringing an app frontmost and revealing its search field is timing-
    # sensitive: a first pass can see the wrong window or a not-yet-ready field.
    # Retrying the verify/navigate cycle a few times absorbs that.
    DEFAULT_NAVIGATE_ATTEMPTS = 3
    DEFAULT_RETRY_SETTLE_SECONDS = 0.6

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
        navigate_attempts: int = DEFAULT_NAVIGATE_ATTEMPTS,
        retry_settle_seconds: float = DEFAULT_RETRY_SETTLE_SECONDS,
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
        self._send_button_queries = {
            key.casefold(): value for key, value in DEFAULT_SEND_BUTTON_QUERIES.items()
        }
        self.search_settle_seconds = max(0.0, float(search_settle_seconds))
        self.navigate_attempts = max(1, int(navigate_attempts))
        self.retry_settle_seconds = max(0.0, float(retry_settle_seconds))
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

    def send_button_query(self, app_name: str) -> str | None:
        """AX query for the send button of a known messaging app."""
        if not isinstance(app_name, str):
            return None

        return self._send_button_queries.get(app_name.strip().casefold())

    def supports_composer_send(self, app_name: str) -> bool:
        """Whether the verified composer-send path exists for this app."""
        return bool(self.composer_query(app_name) and self.send_button_query(app_name))

    def send_text(self, app_name: str, text: str) -> ToolResult:
        """Send a message: focus the composer, type, then press send.

        The WhatsApp composer ignores programmatic focus (AXFocused never
        confirms) and does not treat a set AXValue as real input (the send
        button stays hidden). It does honor AXPress to focus, and real
        keystrokes register as input and reveal the send button. So: press the
        composer to focus it, type the text, then press the send button. The
        send button only exists once text has actually been entered, so its
        absence means the text did not register -- we then report a clean
        failure and send nothing. Delivery is checked by "verify, don't
        assume": the composer emptying after the press is state_confirmed.
        """
        if not isinstance(text, str) or not text.strip():
            return ToolResult.failure(
                action="send_text",
                message="Le message a envoyer est vide.",
                error_code="invalid_text",
            )

        composer = self.composer_query(app_name)
        send_button = self.send_button_query(app_name)
        if not composer or not send_button:
            return ToolResult.failure(
                action="send_text",
                message="L'envoi par champ de saisie n'est pas supporte pour cette application.",
                error_code="composer_unsupported",
            )

        # Clear any residual draft so exactly `text` is sent.
        self.ui_accessibility.set_value(composer, "")

        focus = self.ui_accessibility.activate_ui_element(composer)
        if not focus.ok:
            return ToolResult(
                ok=False,
                action="send_text",
                message="Le champ de saisie n'a pas pu etre active.",
                data=dict(focus.data),
                error_code=focus.error_code or "composer_not_focused",
            )

        typed = self.keyboard.type_text(text)
        if not typed.ok:
            return typed

        self.sleeper(self.search_settle_seconds)
        pressed = self.ui_accessibility.activate_ui_element(send_button)
        if not pressed.ok:
            # No send button means the text never registered as input: fail safe.
            return ToolResult.failure(
                action="send_text",
                message=(
                    "Le message n'a pas pu etre saisi dans le champ (bouton d'envoi "
                    "absent). Rien n'a ete envoye."
                ),
                error_code="composer_not_filled",
            )

        # Verify by effect: a sent message leaves the composer empty.
        self.sleeper(self.search_settle_seconds)
        emptied = False
        after = self.ui_accessibility.read_value(composer)
        if after.ok:
            value = after.data.get("value")
            emptied = value is None or str(value).strip() == ""

        if emptied:
            message = "Message envoye : le champ de saisie s'est vide apres l'envoi."
        else:
            message = (
                "Commande d'envoi envoyee (bouton presse), mais Jarvis n'a pas pu "
                "confirmer que le message est parti."
            )

        return ToolResult.success(
            action="send_text",
            message=message,
            command_executed=True,
            state_confirmed=emptied,
            app=app_name,
            text_length=len(text),
        )

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
        last = self.verify_recipient(app_name, expected_recipient)
        if last.ok:
            return last

        resolvable = (
            last.error_code == "recipient_not_verified"
            and last.data.get("reason") in _NAVIGABLE_REASONS
            and self.search_query(app_name) is not None
        )
        if not resolvable:
            # A definitive wrong chat with no search path won't fix itself.
            return last

        # Bringing the app frontmost and revealing the search field is timing-
        # sensitive (today's no_window / search_field_not_found were transient).
        # Retry only when navigation itself FAILS; if it succeeds but opens the
        # wrong chat, that is a real mismatch -- refuse at once without re-typing.
        for attempt in range(self.navigate_attempts):
            navigation = self.navigate_to_recipient(app_name, expected_recipient)
            if navigation.ok:
                # Re-verify against the header AFTER navigating: the safety net.
                # If the wrong chat (or none) opened, this refuses; nothing is sent.
                return self.verify_recipient(app_name, expected_recipient)

            last = navigation
            if attempt < self.navigate_attempts - 1:
                self.sleeper(self.retry_settle_seconds)

        return last

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

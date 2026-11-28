"""Composite UI interactions built on apps, windows, accessibility, keyboard and clipboard."""
from __future__ import annotations

import time
from typing import Any

from jarvis.capabilities.apps import AppCapability
from jarvis.capabilities.clipboard import ClipboardCapability
from jarvis.capabilities.keyboard import KeyboardCapability
from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
from jarvis.capabilities.windows import WindowCapability
from jarvis.tools.accessibility import normalize_text
from jarvis.capabilities.interaction_typing import InteractionTypingMixin
from jarvis.capabilities.interaction_recovery import InteractionRecoveryMixin
from jarvis.capabilities.interaction_results import InteractionResultsMixin


class InteractionCapability(
    InteractionTypingMixin,
    InteractionRecoveryMixin,
    InteractionResultsMixin,
):
    SEARCH_TOKENS = {"recherche", "search"}
    RECOVERY_TEXT_ROLES = {"AXTextField", "AXTextArea", "AXSearchField"}
    READINESS_RETRYABLE_ERRORS = {"no_window"}
    DEFAULT_READINESS_ATTEMPTS = 3
    DEFAULT_READINESS_DELAY_SECONDS = 0.2
    # Post-copy the system pasteboard can lag a few ms behind Command+C, so the
    # first read may still look empty. These bound a short settle window: a few
    # re-reads max, stopping as soon as the pasteboard is readable. Worst case
    # is (attempts - 1) * delay ~= 0.36 s, never an open-ended wait, and never a
    # second Command+C.
    DEFAULT_CLIPBOARD_READ_ATTEMPTS = 4
    DEFAULT_CLIPBOARD_READ_DELAY_SECONDS = 0.12

    def __init__(
        self,
        apps=None,
        windows=None,
        ui_accessibility=None,
        keyboard=None,
        clipboard=None,
        readiness_attempts: int = DEFAULT_READINESS_ATTEMPTS,
        readiness_delay_seconds: float = DEFAULT_READINESS_DELAY_SECONDS,
        clipboard_read_attempts: int = DEFAULT_CLIPBOARD_READ_ATTEMPTS,
        clipboard_read_delay_seconds: float = DEFAULT_CLIPBOARD_READ_DELAY_SECONDS,
        sleeper=None,
    ):
        self.apps = apps if apps is not None else AppCapability()
        self.windows = windows if windows is not None else WindowCapability()
        self.ui_accessibility = (
            ui_accessibility
            if ui_accessibility is not None
            else UIAccessibilityCapability()
        )
        self.keyboard = keyboard if keyboard is not None else KeyboardCapability()
        self.clipboard = (
            clipboard
            if clipboard is not None
            else ClipboardCapability()
        )
        self.readiness_attempts = max(1, int(readiness_attempts))
        self.readiness_delay_seconds = max(0.0, float(readiness_delay_seconds))
        self.clipboard_read_attempts = max(1, int(clipboard_read_attempts))
        self.clipboard_read_delay_seconds = max(0.0, float(clipboard_read_delay_seconds))
        self.sleeper = sleeper if sleeper is not None else time.sleep

    def select_all_and_copy(self) -> ToolResult:
        """Command+A then Command+C, with a bounded post-copy pasteboard re-read.

        Result field contract:
        - clipboard_verified: the post-copy read of the pasteboard succeeded
          (within the bounded attempts); it does not prove a new copy.
        - clipboard_has_text: the final observed read exposed readable text.
        - clipboard_changed: the final text differs from before (or before had
          no text and after does); staleness alone never sets this.
        - copy_observed / new_copy_proven: has_text AND changed. This is the
          only state that proves a *new* copy landed. before == after is never
          treated as proof of a new copy.
        - clipboard_read_attempts: how many reads the settle window used.
        state_confirmed mirrors new_copy_proven. No raw clipboard text is ever
        placed in the result.
        """
        steps = []
        before_clipboard = self.clipboard.get_clipboard_text()
        steps.append(self._clipboard_step("get_clipboard_text_before", before_clipboard))

        select = self.keyboard.hotkey(["command", "a"])
        steps.append(self._step("hotkey_command_a", select))

        failure = self._require_command_executed(
            "select_all_and_copy",
            "hotkey_command_a",
            select,
            steps,
        )

        if failure is not None:
            return failure

        copy = self.keyboard.hotkey(["command", "c"])
        steps.append(self._step("hotkey_command_c", copy))

        failure = self._require_command_executed(
            "select_all_and_copy",
            "hotkey_command_c",
            copy,
            steps,
        )

        if failure is not None:
            return failure

        after_clipboard, read_attempts = self._observe_clipboard_after_copy(
            before_clipboard,
        )
        steps.append(self._clipboard_step("get_clipboard_text_after", after_clipboard))

        if not after_clipboard.ok:
            return self._failure(
                action="select_all_and_copy",
                failed_step="get_clipboard_text_after",
                steps=steps,
                message=(
                    "La copie a ete envoyee, mais Jarvis n'a pas pu lire le "
                    "presse-papiers apres l'action."
                ),
                error_code=after_clipboard.error_code or "clipboard_read_failed",
                clipboard_verified=False,
                clipboard_has_text=False,
                clipboard_read_attempts=read_attempts,
            )

        clipboard_has_text = after_clipboard.data.get("has_text") is True
        clipboard_length = after_clipboard.data.get("length")
        clipboard_changed = self._clipboard_changed(
            before_clipboard,
            after_clipboard,
        )
        new_copy_observed = clipboard_has_text and clipboard_changed
        state_confirmed = new_copy_observed

        return ToolResult.success(
            action="select_all_and_copy",
            message=(
                "Les commandes selectionner tout puis copier ont ete envoyees "
                "dans l'ordre, puis le presse-papiers a ete relu."
            ),
            command_executed=True,
            state_confirmed=state_confirmed,
            clipboard_verified=True,
            clipboard_has_text=clipboard_has_text,
            clipboard_length=clipboard_length,
            clipboard_changed=clipboard_changed,
            copy_observed=new_copy_observed,
            new_copy_proven=new_copy_observed,
            clipboard_read_attempts=read_attempts,
            steps=steps,
        )

    def select_all_and_delete(self, role: str | None = None) -> ToolResult:
        """Select all then delete the selection in a verified editable target.

        Verifies a single focused, enabled, editable, non-secure field first, so
        the deletion never fires blindly into whatever is frontmost. Then sends
        Command+A and exactly one restricted Backspace, stopping on any failed
        or unexecuted step. No clipboard access, no file deletion, no Mouse
        fallback. state_confirmed stays False: the command is sent, but the
        field being empty cannot be confirmed without reading its value, which
        the privacy design does not do.
        """
        steps: list[dict[str, Any]] = []

        verify_failure = self._verify_focused_editable_target(
            "select_all_and_delete",
            role,
            steps,
        )

        if verify_failure is not None:
            return verify_failure

        select = self.keyboard.hotkey(["command", "a"])
        steps.append(self._step("hotkey_command_a", select))

        failure = self._require_command_executed(
            "select_all_and_delete",
            "hotkey_command_a",
            select,
            steps,
        )

        if failure is not None:
            return failure

        deleted = self.keyboard.delete_selection()
        steps.append(self._step("delete_selection", deleted))

        failure = self._require_command_executed(
            "select_all_and_delete",
            "delete_selection",
            deleted,
            steps,
        )

        if failure is not None:
            return failure

        return ToolResult.success(
            action="select_all_and_delete",
            message=(
                "La cible editable a ete verifiee, puis selectionner tout et "
                "supprimer ont ete envoyes ; l'effacement ne peut pas etre "
                "confirme."
            ),
            command_executed=True,
            state_confirmed=False,
            deletion_executed=True,
            role=role,
            steps=steps,
        )

    def _verify_focused_editable_target(
        self,
        action: str,
        role: str | None,
        steps: list[dict[str, Any]],
    ) -> ToolResult | None:
        """Require exactly one focused, enabled, editable, non-secure field.

        Returns a failure ToolResult when the target cannot be verified (so no
        mutating step runs), or None when it is safe to proceed.
        """
        inspected = self.ui_accessibility.inspect_ui(max_depth=6, max_elements=150)
        steps.append(self._step("inspect_editable_target", inspected))
        focused = [
            element for element in inspected.data.get("elements", [])
            if isinstance(element, dict) and element.get("focused") is True
            and element.get("role") in self.RECOVERY_TEXT_ROLES
        ]
        # Editable text areas (e.g. TextEdit's AXTextArea) do not expose
        # AXEnabled at all, so `enabled` is absent (None) rather than True. The
        # real editability guarantee is a settable AXValue (`editable is True`);
        # here we only reject a field that is *explicitly* disabled.
        verified = (
            inspected.ok and not inspected.data.get("truncated")
            and not inspected.data.get("diagnostics") and len(focused) == 1
            and focused[0].get("enabled") is not False
            and focused[0].get("editable") is True
            and not focused[0].get("secure")
            and focused[0].get("subrole") != "AXSecureTextField"
            and (role is None or normalize_text(role) == normalize_text(focused[0]["role"]))
        )

        if not verified:
            return self._failure(
                action=action,
                failed_step="inspect_editable_target",
                steps=steps,
                message=(
                    "Aucune destination editable focalisee n'a pu etre verifiee. "
                    "Suppression annulee."
                ),
                error_code="editable_target_not_verified",
            )

        return None

    def open_app_and_focus_ui(
        self,
        app_name: str,
        query: str,
        role: str | None = None,
    ) -> ToolResult:
        result = self._open_focus_and_verify_app(
            action="open_app_and_focus_ui",
            app_name=app_name,
        )

        if isinstance(result, ToolResult):
            return result

        steps = result
        focus_ui = self.ui_accessibility.focus_ui_element(query, role)
        steps.append(self._step(
            "focus_ui_element",
            focus_ui,
            query_length=self._safe_len(query),
            role=role,
        ))

        failure = self._require_confirmed(
            "open_app_and_focus_ui",
            "focus_ui_element",
            focus_ui,
            steps,
        )

        if failure is not None:
            return failure

        return ToolResult.success(
            action="open_app_and_focus_ui",
            message="L'application et la cible Accessibility ont ete focalisees.",
            command_executed=True,
            state_confirmed=True,
            target_app=app_name,
            query_length=self._safe_len(query),
            role=role,
            steps=steps,
        )

    def open_app_and_type(
        self,
        app_name: str,
        text: str,
        press_enter: bool = True,
    ) -> ToolResult:
        """Open/focus an app and type into its keyboard focus, no AX field check.

        For apps whose input field is not introspectable via Accessibility (e.g.
        Electron/web apps like Claude, whose composer is a deep contenteditable
        with no identifier or text role). Safety floor: it still confirms the
        requested app is frontmost before typing, so text never lands in another
        app; it just trusts the app's own keyboard focus for the exact field.
        Reserved for low-risk assistant prompts, never for outward messaging.
        """
        result = self._open_focus_and_verify_app(
            action="open_app_and_type",
            app_name=app_name,
        )

        if isinstance(result, ToolResult):
            return result

        steps = result
        typed = self.keyboard.type_text(text)
        steps.append(self._step("type_text", typed, text_length=self._safe_len(text)))

        failure = self._require_command_executed(
            "open_app_and_type", "type_text", typed, steps,
        )

        if failure is not None:
            return failure

        if typed.data.get("command_executed") is not True:
            return self._failure(
                action="open_app_and_type", failed_step="type_text", steps=steps,
                message="L'execution de la saisie n'est pas attestee.",
                error_code="command_not_executed",
            )

        if press_enter:
            enter = self.keyboard.press_key("enter")
            steps.append(self._step("press_key_enter", enter))
            failure = self._require_command_executed(
                "open_app_and_type", "press_key_enter", enter, steps,
            )

            if failure is not None:
                return failure

        return ToolResult.success(
            action="open_app_and_type",
            message=(
                "L'application a ete mise au premier plan et la saisie a ete "
                "envoyee ; l'effet applicatif n'est pas confirme."
            ),
            command_executed=True,
            state_confirmed=False,
            target_app=app_name,
            text_length=self._safe_len(text),
            press_enter=press_enter,
            steps=steps,
        )

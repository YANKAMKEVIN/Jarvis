from __future__ import annotations

import re
import time
from typing import Any

from jarvis.capabilities.apps import AppCapability
from jarvis.capabilities.clipboard import ClipboardCapability
from jarvis.capabilities.keyboard import KeyboardCapability
from jarvis.capabilities.results import ToolResult
from jarvis.capabilities.ui_accessibility import UIAccessibilityCapability
from jarvis.capabilities.windows import WindowCapability
from jarvis.tools.accessibility import normalize_text


class InteractionCapability:
    SEARCH_TOKENS = {"recherche", "search"}
    RECOVERY_TEXT_ROLES = {"AXTextField", "AXTextArea", "AXSearchField"}
    READINESS_RETRYABLE_ERRORS = {"no_window"}
    DEFAULT_READINESS_ATTEMPTS = 3
    DEFAULT_READINESS_DELAY_SECONDS = 0.2

    def __init__(
        self,
        apps=None,
        windows=None,
        ui_accessibility=None,
        keyboard=None,
        clipboard=None,
        readiness_attempts: int = DEFAULT_READINESS_ATTEMPTS,
        readiness_delay_seconds: float = DEFAULT_READINESS_DELAY_SECONDS,
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
        self.sleeper = sleeper if sleeper is not None else time.sleep

    def select_all_and_copy(self) -> ToolResult:
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

        after_clipboard = self.clipboard.get_clipboard_text()
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
            steps=steps,
        )

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

    def focus_app_ui_and_type(
        self,
        app_name: str,
        text: str,
        query: str | None = None,
        role: str | None = None,
        press_enter: bool = False,
    ) -> ToolResult:
        """Type into a named target, or a verified current editable field.

        query=None expresses no semantic destination: it only permits the single
        focused, enabled, non-secure text field with an AX-writable value.
        Command execution does not confirm navigation or application effects.
        """
        result = self._open_focus_and_verify_app(
            action="focus_app_ui_and_type",
            app_name=app_name,
        )

        if isinstance(result, ToolResult):
            return result

        steps = result

        if query is not None:
            focus_ui = self.ui_accessibility.focus_ui_element(query, role)
            steps.append(self._step(
                "focus_ui_element",
                focus_ui,
                query_length=self._safe_len(query),
                role=role,
            ))

            if not focus_ui.ok and focus_ui.error_code == "ui_element_not_found":
                focus_ui = self._recover_ui_focus(
                    action="focus_app_ui_and_type",
                    query=query,
                    role=role,
                    steps=steps,
                )

            failure = self._require_confirmed(
                "focus_app_ui_and_type",
                "focus_ui_element",
                focus_ui,
                steps,
            )

            if failure is not None:
                return failure

        else:
            inspected = self.ui_accessibility.inspect_ui(max_depth=6, max_elements=150)
            steps.append(self._step("inspect_editable_target", inspected))
            focused = [
                element for element in inspected.data.get("elements", [])
                if isinstance(element, dict) and element.get("focused") is True
                and element.get("role") in self.RECOVERY_TEXT_ROLES
            ]
            verified = (
                inspected.ok and not inspected.data.get("truncated")
                and not inspected.data.get("diagnostics") and len(focused) == 1
                and focused[0].get("enabled") is True
                and focused[0].get("editable") is True
                and not focused[0].get("secure")
                and focused[0].get("subrole") != "AXSecureTextField"
                and (role is None or normalize_text(role) == normalize_text(focused[0]["role"]))
            )
            if not verified:
                return self._failure(
                    action="focus_app_ui_and_type",
                    failed_step="inspect_editable_target",
                    steps=steps,
                    message="Aucune destination editable focalisee n'a pu etre verifiee. Fournir query.",
                    error_code="editable_target_not_verified",
                )

        typed = self.keyboard.type_text(text)
        steps.append(self._step(
            "type_text",
            typed,
            text_length=self._safe_len(text),
        ))

        failure = self._require_command_executed(
            "focus_app_ui_and_type",
            "type_text",
            typed,
            steps,
        )

        if failure is not None:
            return failure

        if typed.data.get("command_executed") is not True:
            return self._failure(
                action="focus_app_ui_and_type", failed_step="type_text", steps=steps,
                message="L'execution de la saisie n'est pas attestee.",
                error_code="command_not_executed",
            )

        if press_enter:
            enter = self.keyboard.press_key("enter")
            steps.append(self._step("press_key_enter", enter))
            failure = self._require_command_executed(
                "focus_app_ui_and_type",
                "press_key_enter",
                enter,
                steps,
            )

            if failure is not None:
                return failure

        return ToolResult.success(
            action="focus_app_ui_and_type",
            message=(
                "La cible a ete verifiee et la commande de saisie a ete envoyee."
            ),
            command_executed=True,
            state_confirmed=False,
            text_command_executed=True,
            target_app=app_name,
            query_length=self._safe_len(query),
            text_length=self._safe_len(text),
            role=role,
            press_enter=press_enter,
            steps=steps,
        )

    def _open_focus_and_verify_app(
        self,
        action: str,
        app_name: str,
    ) -> list[dict[str, Any]] | ToolResult:
        steps = []

        opened = self.apps.open_app(app_name)
        steps.append(self._step("open_app", opened, target_app=app_name))
        failure = self._require_ok(action, "open_app", opened, steps)

        if failure is not None:
            return failure

        focused = self._focus_window_with_readiness(app_name, steps)
        failure = self._require_confirmed(action, "focus_window", focused, steps)

        if failure is not None:
            return failure

        active = self.windows.get_active_window()
        observed_app = active.data.get("target_app") if active.ok else None
        steps.append(self._step(
            "get_active_window",
            active,
            target_app=observed_app,
        ))
        failure = self._require_ok(action, "get_active_window", active, steps)

        if failure is not None:
            return failure

        if not self._same_app(app_name, observed_app):
            return self._failure(
                action=action,
                failed_step="get_active_window",
                steps=steps,
                message=(
                    "La fenetre active observee ne correspond pas a "
                    "l'application demandee. La suite a ete arretee."
                ),
                error_code="active_window_mismatch",
                target_app=app_name,
                observed_app=observed_app,
            )

        return steps

    def _focus_window_with_readiness(
        self,
        app_name: str,
        steps: list[dict[str, Any]],
    ) -> ToolResult:
        focused = None

        for attempt in range(1, self.readiness_attempts + 1):
            focused = self.windows.focus_window(app_name)
            steps.append(self._step(
                "focus_window",
                focused,
                target_app=app_name,
                readiness_attempt=attempt,
                readiness_max_attempts=self.readiness_attempts,
            ))

            if focused.ok or focused.error_code not in self.READINESS_RETRYABLE_ERRORS:
                return focused

            if attempt < self.readiness_attempts:
                self.sleeper(self.readiness_delay_seconds)

        return focused

    def _recover_ui_focus(
        self,
        action: str,
        query: str,
        role: str | None,
        steps: list[dict[str, Any]],
    ) -> ToolResult:
        inspected = self.ui_accessibility.inspect_ui(max_depth=6, max_elements=150)
        steps.append(self._step(
            "inspect_ui_recovery",
            inspected,
            recovery_attempted=True,
        ))

        if not inspected.ok:
            return inspected

        candidates = self._recovery_candidates(
            query=query,
            role=role,
            elements=inspected.data.get("elements", []),
        )

        if not candidates:
            return ToolResult(
                ok=False,
                action=action,
                message=(
                    "Aucun candidat Accessibility suffisamment sur n'a ete "
                    "trouve pour recuperer cette cible."
                ),
                data={
                    "query_length": self._safe_len(query),
                    "role": role,
                    "recovery_attempted": True,
                    "recovery_succeeded": False,
                    "candidate_count": 0,
                },
                error_code="ui_element_not_found",
            )

        if len(candidates) > 1:
            return ToolResult(
                ok=False,
                action=action,
                message=(
                    "Plusieurs candidats Accessibility plausibles ont ete "
                    "trouves pendant la recuperation."
                ),
                data={
                    "query_length": self._safe_len(query),
                    "role": role,
                    "recovery_attempted": True,
                    "recovery_succeeded": False,
                    "candidate_count": len(candidates),
                },
                error_code="ambiguous_ui_element",
            )

        recovered_label = self._candidate_label(candidates[0])
        recovered = self.ui_accessibility.focus_ui_element(recovered_label, role)
        steps.append(self._step(
            "focus_ui_element_recovery",
            recovered,
            query_length=self._safe_len(recovered_label),
            role=role,
            recovery_attempted=True,
            recovery_succeeded=recovered.ok and recovered.data.get("state_confirmed") is True,
        ))
        return recovered

    def _recovery_candidates(
        self,
        query: str,
        role: str | None,
        elements: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(elements, list):
            return []

        normalized_query = normalize_text(query)

        if len(normalized_query) <= 1:
            return []

        query_tokens = set(normalized_query.split())

        if not query_tokens.intersection(self.SEARCH_TOKENS):
            return []

        normalized_role = normalize_text(role) if role else None
        candidates = []

        for element in elements:
            if not isinstance(element, dict):
                continue

            element_role = element.get("role")

            if normalized_role and normalize_text(element_role) != normalized_role:
                continue

            if not normalized_role and element_role not in self.RECOVERY_TEXT_ROLES:
                continue

            fields = [
                field
                for field in (
                    element.get("title"),
                    element.get("description"),
                    element.get("identifier"),
                )
                if isinstance(field, str) and field.strip()
            ]

            if any(
                set(re.findall(r"[^\W_]+", normalize_text(field))).intersection(self.SEARCH_TOKENS)
                for field in fields
            ):
                candidates.append(element)

        return candidates

    @staticmethod
    def _candidate_label(candidate: dict[str, Any]) -> str:
        for key in ("title", "description", "identifier"):
            value = candidate.get(key)

            if isinstance(value, str) and value.strip():
                return value

        return ""

    @staticmethod
    def _clipboard_changed(before: ToolResult, after: ToolResult) -> bool:
        if not after.ok or after.data.get("has_text") is not True:
            return False

        if not before.ok:
            return False

        if before.data.get("has_text") is not True:
            return True

        return before.data.get("text") != after.data.get("text")

    def _require_ok(
        self,
        action: str,
        step_name: str,
        result: ToolResult,
        steps: list[dict[str, Any]],
    ) -> ToolResult | None:
        if result.ok:
            return None

        return self._failure(
            action=action,
            failed_step=step_name,
            steps=steps,
            message=(
                f"L'etape {step_name} a echoue. Les etapes dependantes "
                "n'ont pas ete lancees."
            ),
            error_code=result.error_code or "dependency_failed",
        )

    def _require_command_executed(
        self,
        action: str,
        step_name: str,
        result: ToolResult,
        steps: list[dict[str, Any]],
    ) -> ToolResult | None:
        failure = self._require_ok(action, step_name, result, steps)

        if failure is not None:
            return failure

        if result.data.get("command_executed") is not False:
            return None

        return self._failure(
            action=action,
            failed_step=step_name,
            steps=steps,
            message=(
                f"L'etape {step_name} n'a pas execute sa commande. "
                "Les etapes dependantes n'ont pas ete lancees."
            ),
            error_code="command_not_executed",
        )

    def _require_confirmed(
        self,
        action: str,
        step_name: str,
        result: ToolResult,
        steps: list[dict[str, Any]],
    ) -> ToolResult | None:
        failure = self._require_command_executed(action, step_name, result, steps)

        if failure is not None:
            return failure

        if result.data.get("state_confirmed") is True:
            return None

        return self._failure(
            action=action,
            failed_step=step_name,
            steps=steps,
            message=(
                f"L'etape {step_name} n'a pas confirme son etat final. "
                "Les etapes dependantes n'ont pas ete lancees."
            ),
            error_code="state_not_confirmed",
        )

    @staticmethod
    def _failure(
        action: str,
        failed_step: str,
        steps: list[dict[str, Any]],
        message: str,
        error_code: str,
        **data: Any,
    ) -> ToolResult:
        return ToolResult(
            ok=False,
            action=action,
            message=message,
            data={
                "failed_step": failed_step,
                "steps": steps,
                "command_executed": any(step.get("command_executed") is True for step in steps),
                "state_confirmed": False,
                "text_command_executed": any(
                    step["name"] == "type_text" and step.get("command_executed") is True
                    for step in steps
                ),
                **data,
            },
            error_code=error_code,
        )

    @staticmethod
    def _step(
        name: str,
        result: ToolResult,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "name": name,
            "action": result.action,
            "ok": result.ok,
            "error_code": result.error_code,
            "requires_confirmation": result.requires_confirmation,
            "command_executed": result.data.get("command_executed"),
            "state_confirmed": result.data.get("state_confirmed"),
            **{
                key: value
                for key, value in extra.items()
                if value is not None
            },
        }

    @staticmethod
    def _clipboard_step(name: str, result: ToolResult) -> dict[str, Any]:
        return {
            "name": name,
            "action": result.action,
            "ok": result.ok,
            "error_code": result.error_code,
            "has_text": result.data.get("has_text"),
            "length": result.data.get("length"),
            "returned_length": result.data.get("returned_length"),
            "truncated": result.data.get("truncated"),
        }

    @staticmethod
    def _safe_len(value: str | None) -> int | None:
        return len(value) if isinstance(value, str) else None

    @staticmethod
    def _same_app(expected: str, observed: Any) -> bool:
        if not isinstance(expected, str) or not isinstance(observed, str):
            return False

        return expected.strip().casefold() == observed.strip().casefold()

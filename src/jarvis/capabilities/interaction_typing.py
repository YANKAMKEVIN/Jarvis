"""Composite flow: focus an app UI element, verify it, then type."""
from __future__ import annotations

from typing import Any

from jarvis.capabilities.results import ToolResult
from jarvis.tools.accessibility import normalize_text


class InteractionTypingMixin:
    """Composite flow: focus an app UI element, verify it, then type. Mixed into InteractionCapability."""

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

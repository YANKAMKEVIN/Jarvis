"""Step bookkeeping, result checks and clipboard observation for composites."""
from __future__ import annotations

from typing import Any

from jarvis.capabilities.results import ToolResult


class InteractionResultsMixin:
    """Step bookkeeping, result checks and clipboard observation for composites. Mixed into InteractionCapability."""

    def _observe_clipboard_after_copy(self, before) -> tuple[Any, int]:
        """Re-read the pasteboard a bounded number of times after a copy.

        Stops as soon as the read is usable (readable text observed) or fails,
        otherwise waits a short delay and retries, up to clipboard_read_attempts.
        Never re-issues Command+C. Returns the last read and the attempt count.
        """
        after = before
        attempts = 0

        for attempt in range(1, self.clipboard_read_attempts + 1):
            attempts = attempt
            after = self.clipboard.get_clipboard_text()

            if not after.ok:
                break

            if after.data.get("has_text") is True:
                break

            if attempt < self.clipboard_read_attempts:
                self.sleeper(self.clipboard_read_delay_seconds)

        return after, attempts

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

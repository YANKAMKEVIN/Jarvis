from dataclasses import dataclass, field
from typing import Any


class CapabilityError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    action: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    requires_confirmation: bool = False
    reason: str | None = None

    @classmethod
    def success(
        cls,
        action: str,
        message: str,
        **data: Any,
    ) -> "ToolResult":
        return cls(
            ok=True,
            action=action,
            message=message,
            data=data,
        )

    @classmethod
    def failure(
        cls,
        action: str,
        message: str,
        error_code: str | None = None,
        requires_confirmation: bool = False,
        reason: str | None = None,
    ) -> "ToolResult":
        return cls(
            ok=False,
            action=action,
            message=message,
            error_code=error_code,
            requires_confirmation=requires_confirmation,
            reason=reason,
        )

    def to_livekit_dict(self) -> dict[str, Any]:
        payload = {
            "ok": self.ok,
            "action": self.action,
            **self.data,
            "message": self.message,
        }

        if self.reason:
            payload["reason"] = self.reason

        if self.error_code:
            payload["error_code"] = self.error_code

        if self.requires_confirmation:
            payload["requires_confirmation"] = self.requires_confirmation

        return payload

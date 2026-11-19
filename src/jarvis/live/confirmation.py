from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable


# Executor runs the real, side-effectful action and returns its ToolResult. It
# is captured at preparation time and only invoked on explicit confirmation.
ActionExecutor = Callable[[], Any]


class ConfirmationNeedsUserTurn(Exception):
    """confirm() was called before the user spoke since the preparation.

    The token is left pending: the model must ask the user to confirm aloud
    and call confirm_action again once the user has answered.
    """


@dataclass
class PendingAction:
    token: str
    action: str
    executor: ActionExecutor
    created_at: float
    user_turn: int = 0


class PendingActionStore:
    """Holds outward actions that await an explicit user confirmation.

    An action is registered without any side effect and identified by a single
    short-lived, single-use token. It only runs when confirm() hands the stored
    executor back to the caller. This is the gate for anything outward (sending
    a message): prepare -> speak a summary -> user says yes -> confirm.

    The store keeps no message content and logs nothing; the executor closure
    carries whatever the action needs, and callers never echo it.

    A token alone is not enough: the model could call confirm_action on its
    own (for instance driven by a prompt injection in a web page or message).
    The runtime calls note_user_turn() whenever the user says or types
    something, and confirm() only accepts an action if at least one user turn
    was noted after it was prepared.
    """

    DEFAULT_TTL_SECONDS = 300.0
    DEFAULT_MAX_PENDING = 8

    def __init__(
        self,
        clock: Callable[[], float] | None = None,
        token_factory: Callable[[], str] | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_pending: int = DEFAULT_MAX_PENDING,
    ):
        self._clock = clock if clock is not None else time.monotonic
        self._token_factory = token_factory or (lambda: secrets.token_hex(8))
        self._ttl_seconds = float(ttl_seconds)
        self._max_pending = max(1, int(max_pending))
        self._pending: dict[str, PendingAction] = {}
        self._user_turn = 0

    def note_user_turn(self) -> None:
        """Record that the user spoke or typed since the last call."""
        self._user_turn += 1

    def register(self, action: str, executor: ActionExecutor) -> str:
        self._prune()
        token = self._token_factory()
        self._pending[token] = PendingAction(
            token=token,
            action=action,
            executor=executor,
            created_at=self._clock(),
            user_turn=self._user_turn,
        )

        # Bound memory: drop the oldest if we somehow exceed the cap.
        while len(self._pending) > self._max_pending:
            oldest = min(self._pending.values(), key=lambda item: item.created_at)
            self._pending.pop(oldest.token, None)

        return token

    def confirm(self, token: str) -> PendingAction | None:
        """Consume and return the pending action, or None if unknown/expired.

        Raises ConfirmationNeedsUserTurn, without consuming the token, when
        the user has not spoken since the action was prepared.
        """
        self._prune()

        if not isinstance(token, str):
            return None

        pending = self._pending.get(token)
        if pending is None:
            return None
        if self._user_turn <= pending.user_turn:
            raise ConfirmationNeedsUserTurn(pending.action)

        return self._pending.pop(token)

    def cancel(self, token: str) -> PendingAction | None:
        self._prune()

        if not isinstance(token, str):
            return None

        return self._pending.pop(token, None)

    def has_pending(self) -> bool:
        self._prune()
        return bool(self._pending)

    def _prune(self) -> None:
        now = self._clock()
        expired = [
            token
            for token, item in self._pending.items()
            if now - item.created_at > self._ttl_seconds
        ]

        for token in expired:
            self._pending.pop(token, None)


def note_user_turn_from_text(registry: Any, text: Any) -> bool:
    """Note a user turn on registry when the user said or typed something.

    Wired to the session's user transcriptions (partial ones included: the
    final transcript only arrives after the model has answered) and to user
    conversation items (typed text).
    """
    if not isinstance(text, str) or not text.strip():
        return False
    note = getattr(registry, "note_user_turn", None)
    if note is None:
        return False
    note()
    return True

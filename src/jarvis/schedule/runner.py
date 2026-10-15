"""Deliver due scheduled messages.

Run on a schedule (a launchd agent polling every minute). Each pass sends the
messages that are due and deliverable now; anything not deliverable yet (screen
locked, recipient not verifiable, send unconfirmed) is kept pending and retried
on later passes, until a grace window elapses -- then it is marked failed and
the user is notified. The recipient is always re-verified at send time, and a
send that cannot be confirmed never counts as sent.
"""

from __future__ import annotations

import subprocess
import time
from typing import Any, Callable


# How long after its due time a message keeps being retried while it cannot be
# delivered (e.g. the Mac is locked), before it is marked failed.
DEFAULT_GRACE_SECONDS = 30 * 60


def deliver_due(
    store,
    messaging,
    *,
    screen_unlocked: Callable[[], bool],
    now: float | None = None,
    grace_seconds: float = DEFAULT_GRACE_SECONDS,
    notifier: Callable[[str], None] | None = None,
) -> dict[str, list]:
    """Send every due, deliverable message once. Returns a per-outcome summary."""
    moment = time.time() if now is None else float(now)
    results: dict[str, list] = {"sent": [], "failed": [], "deferred": []}

    for row in store.due(moment):
        row_id = row["id"]
        app = row["app"]
        recipient = row["recipient"]
        text = row["text"]
        within_grace = moment <= row["due_at"] + grace_seconds

        def settle(reason: str) -> None:
            # Transient problem: retry within grace, otherwise give up + notify.
            if within_grace:
                store.record_attempt(row_id, reason)
                results["deferred"].append((row_id, reason))
            else:
                store.mark_failed(row_id, reason)
                results["failed"].append((row_id, reason))
                _notify(
                    notifier,
                    f"Message planifie non envoye a {recipient} : {reason}.",
                )

        if not screen_unlocked():
            settle("ecran verrouille")
            continue

        verify = messaging.ensure_recipient(app, recipient)
        if not getattr(verify, "ok", False):
            settle(getattr(verify, "error_code", None) or "destinataire non verifie")
            continue

        sent = messaging.send_text(app, text)
        if getattr(sent, "ok", False):
            store.mark_sent(row_id)
            results["sent"].append(row_id)
            _notify(notifier, f"Message planifie envoye a {recipient}.")
        else:
            settle(getattr(sent, "error_code", None) or "echec d'envoi")

    return results


def _notify(notifier: Callable[[str], None] | None, message: str) -> None:
    if notifier is None:
        return
    try:
        notifier(message)
    except Exception:
        pass


def macos_screen_unlocked() -> bool:
    """True unless the macOS login/lock window is frontmost."""
    try:
        asn = subprocess.run(
            ["lsappinfo", "front"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        info = subprocess.run(
            ["lsappinfo", "info", "-only", "name", asn],
            capture_output=True, text=True, timeout=5,
        ).stdout
        name = info.split("=", 1)[-1].strip().strip('"')
        return name != "loginwindow"
    except Exception:
        return False


def macos_notifier(message: str) -> None:
    """Post a macOS notification (best effort)."""
    safe = message.replace('"', "'")
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe}" with title "Jarvis"'],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass

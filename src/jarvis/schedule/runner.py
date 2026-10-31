"""Deliver due scheduled messages.

Run on a schedule (a launchd agent polling every minute). Missing safe
preconditions (screen locked, recipient unverified) are retried within a grace
window. Once a send starts, its durable claim prevents unattended repetition
following a crash. Only an explicitly confirmed effect counts as sent. An
uncertain outcome is exposed for manual reconciliation; it is never retried
automatically. Scheduled delivery workers serialize their GUI actions per store.
"""

from __future__ import annotations

import subprocess
import re
import os
import fcntl
from contextlib import contextmanager
import time
from typing import Callable



# How long after its due time a message keeps being retried while it cannot be
# delivered (e.g. the Mac is locked), before it is marked failed.
DEFAULT_GRACE_SECONDS = 30 * 60


@contextmanager
def _delivery_lock(store):
    # A stable sidecar serializes GUI delivery for this store across processes.
    descriptor = os.open(str(store.path.resolve())+'.delivery.lock', os.O_CREAT | os.O_RDWR | getattr(os,'O_NOFOLLOW',0), 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def deliver_due(
    store, messaging, *, screen_unlocked: Callable[[], bool],
    now: float | None = None, grace_seconds: float = DEFAULT_GRACE_SECONDS,
    notifier: Callable[[str], None] | None = None,
) -> dict[str, list]:
    """Only confirmed sends succeed; uncertain outcomes never retry unattended."""
    moment = time.time() if now is None else float(now)
    results: dict[str,list] = {'sent': [], 'failed': [], 'deferred': []}
    for row in store.due(moment):
        with _delivery_lock(store):
            row_id = row['id']
            if not store.claim_delivery(row_id):
                continue
            recipient = row['recipient']
            within_grace = moment <= row['due_at'] + grace_seconds

            def fail(reason, uncertain=False):
                store.mark_failed(row_id, reason)
                results['failed'].append((row_id,reason))
                label = "non confirme" if uncertain else "non envoye"
                _notify(notifier, f"Message planifie {label} pour {recipient} : {reason}.")

            # API sends (Telegram) need no unlocked screen; UI sends do.
            needs_screen = getattr(messaging, 'requires_unlocked_screen', lambda _app: True)(row['app']) is not False

            def settle(reason):
                if within_grace:
                    store.record_attempt(row_id,reason)
                    results['deferred'].append((row_id,reason))
                else:
                    fail(reason)

            try:
                unlocked = screen_unlocked() if needs_screen else True
            except Exception:
                unlocked = False
            if unlocked is not True:
                settle('ecran verrouille')
                continue
            try:
                verify = messaging.ensure_recipient(row['app'],recipient)
            except Exception:
                settle('verification du destinataire indisponible')
                continue
            if getattr(verify,'ok',False) is not True:
                settle(getattr(verify,'error_code',None) or 'destinataire non verifie')
                continue
            try:
                still_unlocked = screen_unlocked() if needs_screen else True
            except Exception:
                still_unlocked = False
            if still_unlocked is not True:
                settle('ecran verrouille')
                continue
            try:
                sent = messaging.send_text(row['app'],row['text'],recipient=recipient)
            except Exception:
                fail('envoi incertain ; verifier la conversation avant toute nouvelle tentative', uncertain=True)
                continue
            data = getattr(sent,'data',{})
            if not isinstance(data,dict):
                data = {}
            if getattr(sent,'ok',False) is True and data.get('state_confirmed') is True:
                # A DB failure leaves the durable sending claim, preventing a
                # resend after an external effect whose settlement is unknown.
                store.complete_delivery(row_id,moment)
                results['sent'].append(row_id)
                _notify(notifier, f"Message planifie envoye a {recipient}.")
            elif (not getattr(sent,'ok',False) and not data.get('command_executed')
                  and getattr(sent,'error_code',None) in {'composer_not_filled','composer_not_visible','composer_unsupported','invalid_text',
                       'recipient_not_verified','telegram_not_configured','telegram_not_authorized','telegram_connect_failed','telegram_dialogs_failed'}):
                settle(sent.error_code)
            else:
                fail('envoi incertain ; verifier la conversation avant toute nouvelle tentative', uncertain=True)
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
        front = subprocess.run(['lsappinfo','front'],capture_output=True,text=True,timeout=5)
        asn = front.stdout.strip()
        if front.returncode != 0 or not asn.startswith('ASN:'):
            return False
        info = subprocess.run(['lsappinfo','info','-only','name',asn],capture_output=True,text=True,timeout=5)
        if info.returncode != 0:
            return False
        match = re.fullmatch(r'\s*"LSDisplayName"\s*=\s*"([^"\r\n]+)"\s*',info.stdout)
        return bool(match and match.group(1) != 'loginwindow')
    except Exception:
        return False


def macos_notifier(message: str) -> bool:
    """Report OS acceptance; arbitrary notification content stays an argument."""
    script = 'on run argv\ndisplay notification (item 1 of argv) with title "Jarvis"\nend run'
    try:
        result = subprocess.run(
            ["osascript", "-e", script, "--", message],
            capture_output=True, timeout=5,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False

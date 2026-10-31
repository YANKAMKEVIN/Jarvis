"""Telegram user-account API backend (Telethon / MTProto), no UI automation.

Why an API and not the app's accessibility tree: the native macOS Telegram app
(ru.keepcoder.Telegram 12.6) exposes nothing of its window content to
Accessibility (AXChildren fails on the window), so the conversation header can
never be read and a UI-driven send could never verify its recipient.

Credentials are NEVER handled by the assistant: the user sets them up and logs
in once from a terminal. Telethon is an optional dependency (extra "telegram"),
imported lazily so Jarvis runs without it.

    JARVIS_TELEGRAM_API_ID, JARVIS_TELEGRAM_API_HASH  (from my.telegram.org),
        else Keychain items service "jarvis-telegram", accounts "api_id" and
        "api_hash".
    JARVIS_TELEGRAM_SESSION  session file path (default
        ~/Library/Application Support/Jarvis/telegram/jarvis.session).

    PYTHONPATH=src .venv/bin/python -m jarvis.tools.telegram_api login
    PYTHONPATH=src .venv/bin/python -m jarvis.tools.telegram_api status

The session file grants full access to the Telegram account: it is created in a
0700 directory and chmod 0600.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Callable


KEYCHAIN_SERVICE = "jarvis-telegram"
SELF_PEER = "me"
DEFAULT_DIALOG_LIMIT = 300
DEFAULT_CALL_TIMEOUT = 30.0


class TelegramApiError(Exception):
    """A Telegram API failure. `may_have_sent` is True only when the send
    request may have reached Telegram (the outcome is then unknown)."""

    def __init__(self, message: str, code: str, may_have_sent: bool = False):
        super().__init__(message)
        self.message = message
        self.code = code
        self.may_have_sent = may_have_sent


def default_session_path() -> Path:
    override = os.environ.get("JARVIS_TELEGRAM_SESSION")
    if override:
        return Path(override).expanduser()
    return (
        Path.home() / "Library" / "Application Support" / "Jarvis"
        / "telegram" / "jarvis.session"
    )


def _keychain_secret(account: str) -> str | None:
    try:
        completed = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", account, "-w"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def default_credentials() -> tuple[int | None, str | None]:
    raw_id = os.environ.get("JARVIS_TELEGRAM_API_ID") or _keychain_secret("api_id")
    api_hash = os.environ.get("JARVIS_TELEGRAM_API_HASH") or _keychain_secret("api_hash")
    try:
        api_id = int(raw_id) if raw_id else None
    except ValueError:
        api_id = None
    return api_id, api_hash


def _telethon_client_factory(session: str, api_id: int, api_hash: str):
    try:
        from telethon import TelegramClient
    except ImportError as error:
        raise TelegramApiError(
            "Le module telethon n'est pas installe (pip install -e '.[telegram]').",
            "telegram_not_installed",
        ) from error
    return TelegramClient(session, api_id, api_hash)


def _session_name(path: Path) -> str:
    # Telethon appends ".session" itself.
    text = str(path)
    return text[: -len(".session")] if text.endswith(".session") else text


def _secure_session_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)


def _secure_session_file(path: Path) -> None:
    if path.exists():
        os.chmod(path, 0o600)


class TelethonBackend:
    """Synchronous facade over a Telethon client living on its own event loop.

    Jarvis calls messaging from worker threads (asyncio.to_thread) and from the
    scheduler CLI; Telethon is asyncio-bound to the loop it was created on, so
    one private loop thread owns the client. Never prompts: an unauthorized
    session is reported as telegram_not_authorized (login is a terminal step).
    """

    def __init__(
        self,
        api_id: int | None = None,
        api_hash: str | None = None,
        session_path: Path | None = None,
        client_factory: Callable[[str, int, str], Any] | None = None,
        timeout: float = DEFAULT_CALL_TIMEOUT,
    ):
        if api_id is None and api_hash is None:
            api_id, api_hash = default_credentials()
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = Path(session_path) if session_path else default_session_path()
        self._client_factory = client_factory or _telethon_client_factory
        self.timeout = timeout
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = None
        self._lock = threading.Lock()

    def configured(self) -> bool:
        return bool(self.api_id and self.api_hash and self.session_path.exists())

    def list_dialogs(self, limit: int = DEFAULT_DIALOG_LIMIT) -> list[dict[str, Any]]:
        """Recent conversations: [{id, name, username, kind}], newest first."""
        async def run(client):
            dialogs = []
            async for dialog in client.iter_dialogs(limit=limit):
                entity = getattr(dialog, "entity", None)
                if getattr(dialog, "is_user", False):
                    kind = "bot" if getattr(entity, "bot", False) else "user"
                elif getattr(dialog, "is_group", False):
                    kind = "group"
                else:
                    kind = "channel"
                dialogs.append({
                    "id": dialog.id,
                    "name": dialog.name or "",
                    "username": getattr(entity, "username", None),
                    "kind": kind,
                    "is_self": bool(getattr(entity, "is_self", False)),
                })
            return dialogs

        return self._call(run, "telegram_dialogs_failed")

    def send_message(self, peer: Any, text: str) -> int:
        """Send `text` to `peer` (dialog id or SELF_PEER); returns the message id
        Telegram assigned, which is the proof of delivery to the server."""
        async def run(client):
            message = await client.send_message(peer, text)
            message_id = getattr(message, "id", None)
            if not isinstance(message_id, int):
                raise TelegramApiError(
                    "Telegram n'a pas renvoye d'identifiant de message.",
                    "telegram_send_unconfirmed",
                    may_have_sent=True,
                )
            return message_id

        return self._call(run, "telegram_send_failed", may_have_sent=True)

    def close(self) -> None:
        with self._lock:
            loop, client = self._loop, self._client
            self._loop = self._client = None
        if loop is None:
            return
        if client is not None:
            try:
                asyncio.run_coroutine_threadsafe(client.disconnect(), loop).result(5)
            except Exception:
                pass
        loop.call_soon_threadsafe(loop.stop)

    def _call(self, operation, error_code: str, may_have_sent: bool = False):
        if not (self.api_id and self.api_hash):
            raise TelegramApiError(
                "Telegram n'est pas configure (JARVIS_TELEGRAM_API_ID / "
                "JARVIS_TELEGRAM_API_HASH ou Trousseau).",
                "telegram_not_configured",
            )
        if not self.session_path.exists():
            raise TelegramApiError(
                "Aucune session Telegram : lance une fois "
                "'python -m jarvis.tools.telegram_api login' dans un terminal.",
                "telegram_not_configured",
            )
        loop = self._ensure_loop()
        client = self._ensure_client(loop)
        future = asyncio.run_coroutine_threadsafe(operation(client), loop)
        try:
            return future.result(self.timeout)
        except TelegramApiError:
            raise
        except Exception as error:
            raise TelegramApiError(
                f"Erreur Telegram : {type(error).__name__}.",
                error_code,
                may_have_sent=may_have_sent,
            ) from error

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                thread = threading.Thread(
                    target=loop.run_forever, name="jarvis-telegram", daemon=True,
                )
                thread.start()
                self._loop = loop
            return self._loop

    def _ensure_client(self, loop):
        with self._lock:
            if self._client is not None:
                return self._client

        async def connect():
            client = self._client_factory(
                _session_name(self.session_path), self.api_id, self.api_hash,
            )
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                raise TelegramApiError(
                    "La session Telegram n'est pas connectee : relance "
                    "'python -m jarvis.tools.telegram_api login'.",
                    "telegram_not_authorized",
                )
            return client

        try:
            client = asyncio.run_coroutine_threadsafe(connect(), loop).result(self.timeout)
        except TelegramApiError:
            raise
        except Exception as error:
            raise TelegramApiError(
                f"Connexion a Telegram impossible : {type(error).__name__}.",
                "telegram_connect_failed",
            ) from error
        _secure_session_file(self.session_path)
        with self._lock:
            self._client = client
        return client


def _login() -> int:
    """Interactive one-time login, run by the user in a terminal."""
    api_id, api_hash = default_credentials()
    if not (api_id and api_hash):
        print(
            "Definis d'abord JARVIS_TELEGRAM_API_ID et JARVIS_TELEGRAM_API_HASH "
            "(ou les entrees Trousseau service 'jarvis-telegram', comptes "
            "'api_id' et 'api_hash'), obtenus sur https://my.telegram.org."
        )
        return 1
    path = default_session_path()
    _secure_session_dir(path)
    try:
        import telethon.sync  # noqa: F401  (makes client methods callable synchronously)
    except ImportError:
        print("Le module telethon n'est pas installe (pip install -e '.[telegram]').")
        return 1
    client = _telethon_client_factory(_session_name(path), api_id, api_hash)
    # Telethon has just created the session file: make it private before any
    # authorization key is written into it.
    _secure_session_file(path)
    # Telethon prompts for phone, code and 2FA password on stdin.
    try:
        client.start()
        me = client.get_me()
    finally:
        client.disconnect()
        _secure_session_file(path)
    print(f"Session Telegram enregistree ({path}) pour le compte id {me.id}.")
    return 0


def _status() -> int:
    backend = TelethonBackend()
    if not backend.configured():
        print("Telegram non configure (identifiants API ou session manquants).")
        return 1
    try:
        count = len(backend.list_dialogs(limit=20))
    except TelegramApiError as error:
        print(f"Telegram indisponible : {error.code}")
        return 1
    finally:
        backend.close()
    print(f"Telegram connecte ({count} conversations recentes lues).")
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command == "login":
        raise SystemExit(_login())
    raise SystemExit(_status())

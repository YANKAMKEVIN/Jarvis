"""Fast unread-mail reads over IMAP (solidify path for Apple Mail reads).

Credentials are NEVER handled by the assistant: the host/user come from
environment variables and the password from the macOS Keychain (or an env var)
that the user sets up themselves. The IMAP connection is injectable so the
reader is fully testable without a server or any real account.

    JARVIS_IMAP_HOST, JARVIS_IMAP_PORT (default 993), JARVIS_IMAP_USER
    password: JARVIS_IMAP_PASSWORD, else Keychain item
              (service "jarvis-imap", account = the user).
"""

from __future__ import annotations

import email
import imaplib
import os
import subprocess
from email.header import decode_header
from typing import Any, Callable

from jarvis.tools.mail import MailError


KEYCHAIN_SERVICE = "jarvis-imap"


def _default_connector(host: str, port: int):
    return imaplib.IMAP4_SSL(host, port)


def _keychain_password(username: str) -> str | None:
    try:
        completed = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", username, "-w"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    password = completed.stdout.strip()
    return password or None


class ImapMailReader:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        connector: Callable[[str, int], Any] | None = None,
        password_lookup: Callable[[], str | None] | None = None,
    ):
        self.host = host or os.environ.get("JARVIS_IMAP_HOST")
        self.port = int(port or os.environ.get("JARVIS_IMAP_PORT") or 993)
        self.username = username or os.environ.get("JARVIS_IMAP_USER")
        self._connector = connector or _default_connector
        self._password_lookup = password_lookup or self._default_password

    def configured(self) -> bool:
        return bool(self.host and self.username)

    def _default_password(self) -> str | None:
        return os.environ.get("JARVIS_IMAP_PASSWORD") or (
            _keychain_password(self.username) if self.username else None
        )

    def list_unread(self, limit: int = 10) -> dict[str, Any]:
        if not self.configured():
            raise MailError(
                "IMAP n'est pas configure (JARVIS_IMAP_HOST / JARVIS_IMAP_USER).",
                "imap_not_configured",
            )
        password = self._password_lookup()
        if not password:
            raise MailError(
                "Mot de passe IMAP introuvable (JARVIS_IMAP_PASSWORD ou Trousseau).",
                "imap_no_password",
            )

        cap = max(1, min(int(limit), 50))
        try:
            client = self._connector(self.host, self.port)
        except Exception as error:
            raise MailError(f"Connexion IMAP impossible : {error}", "imap_connect_failed")

        try:
            client.login(self.username, password)
            client.select("INBOX")
            typ, data = client.search(None, "UNSEEN")
            ids = data[0].split() if data and data[0] else []
            ids = list(reversed(ids))[:cap]  # most recent unread first

            emails = []
            for message_id in ids:
                typ, fetched = client.fetch(
                    message_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])"
                )
                raw = self._header_bytes(fetched)
                if raw is None:
                    continue
                parsed = email.message_from_bytes(raw)
                emails.append(
                    {
                        "subject": _decode(parsed.get("Subject")),
                        "sender": _decode(parsed.get("From")),
                        "received": _decode(parsed.get("Date")),
                    }
                )
        except MailError:
            raise
        except Exception as error:
            raise MailError(f"Lecture IMAP impossible : {error}", "imap_read_failed")
        finally:
            try:
                client.logout()
            except Exception:
                pass

        return {"emails": emails, "unread_count": len(emails)}

    def list_unread_with_bodies(self, limit: int = 5, max_body_chars: int = 1500) -> dict[str, Any]:
        """Unread messages with a bounded plain-text body, for local summaries.

        Uses BODY.PEEK[] so reading a message to summarize it does NOT mark it
        as read. Bodies are bounded per message; attachments are ignored.
        """
        if not self.configured():
            raise MailError(
                "IMAP n'est pas configure (JARVIS_IMAP_HOST / JARVIS_IMAP_USER).",
                "imap_not_configured",
            )
        password = self._password_lookup()
        if not password:
            raise MailError(
                "Mot de passe IMAP introuvable (JARVIS_IMAP_PASSWORD ou Trousseau).",
                "imap_no_password",
            )

        cap = max(1, min(int(limit), 20))
        body_cap = max(200, min(int(max_body_chars), 4000))
        try:
            client = self._connector(self.host, self.port)
        except Exception as error:
            raise MailError(f"Connexion IMAP impossible : {error}", "imap_connect_failed")

        try:
            client.login(self.username, password)
            client.select("INBOX")
            typ, data = client.search(None, "UNSEEN")
            ids = data[0].split() if data and data[0] else []
            ids = list(reversed(ids))[:cap]  # most recent unread first

            emails = []
            for message_id in ids:
                typ, fetched = client.fetch(message_id, "(BODY.PEEK[])")
                raw = self._header_bytes(fetched)
                if raw is None:
                    continue
                parsed = email.message_from_bytes(raw)
                emails.append(
                    {
                        "subject": _decode(parsed.get("Subject")),
                        "sender": _decode(parsed.get("From")),
                        "received": _decode(parsed.get("Date")),
                        "body": _plain_body(parsed, body_cap),
                    }
                )
        except MailError:
            raise
        except Exception as error:
            raise MailError(f"Lecture IMAP impossible : {error}", "imap_read_failed")
        finally:
            try:
                client.logout()
            except Exception:
                pass

        return {"emails": emails, "unread_count": len(emails)}

    @staticmethod
    def _header_bytes(fetched) -> bytes | None:
        if not fetched:
            return None
        first = fetched[0]
        if isinstance(first, tuple) and len(first) >= 2:
            value = first[1]
            return value if isinstance(value, bytes) else str(value).encode("utf-8")
        return None


def _part_text(part) -> str:
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        return ""
    if not isinstance(payload, (bytes, bytearray)):
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, TypeError):
        return payload.decode("utf-8", errors="replace")


def _strip_html(text: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"&[a-zA-Z#0-9]+;", " ", text)


def _plain_body(parsed, max_chars: int) -> str:
    """A bounded plain-text view of a message, preferring text/plain."""
    text = ""
    if parsed.is_multipart():
        for part in parsed.walk():
            disposition = str(part.get("Content-Disposition") or "")
            if part.get_content_type() == "text/plain" and "attachment" not in disposition:
                text = _part_text(part)
                if text.strip():
                    break
        if not text.strip():
            for part in parsed.walk():
                disposition = str(part.get("Content-Disposition") or "")
                if part.get_content_type() == "text/html" and "attachment" not in disposition:
                    text = _strip_html(_part_text(part))
                    if text.strip():
                        break
    else:
        text = _part_text(parsed)
        if parsed.get_content_type() == "text/html":
            text = _strip_html(text)
    return " ".join(text.split())[:max_chars]


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            try:
                parts.append(text.decode(charset or "utf-8", errors="replace"))
            except (LookupError, TypeError):
                parts.append(text.decode("utf-8", errors="replace"))
        else:
            parts.append(text)
    return " ".join(" ".join(parts).split())

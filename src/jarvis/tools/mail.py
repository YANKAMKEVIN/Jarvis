"""Read unread mail and create drafts in Apple Mail via AppleScript.

Local-first, injectable runner for tests. Reading is bounded (Mail can be slow)
and returns a clear timeout rather than hanging. Drafting creates an unsent
draft only -- it never sends.
"""

from __future__ import annotations

import subprocess
from typing import Any, Callable


OsascriptRunner = Callable[[str], tuple[int, str, str]]

FIELD_SEP = "\u001f"
RECORD_SEP = "\u001e"
DEFAULT_TIMEOUT_SECONDS = 12
MAX_SNIPPET_CHARS = 200


class MailError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


def _default_runner(script: str) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return 1, "", "__timeout__"
    return completed.returncode, completed.stdout, completed.stderr


class MailTools:
    def __init__(self, runner: OsascriptRunner | None = None):
        self._run = runner if runner is not None else _default_runner

    def list_unread(self, limit: int = 10) -> dict[str, Any]:
        cap = max(1, min(int(limit), 50))
        script = f"""
set out to ""
set n to 0
tell application "Mail"
  set msgs to (messages of inbox whose read status is false)
  repeat with m in msgs
    if n is greater than or equal to {cap} then exit repeat
    set out to out & (subject of m) & "{FIELD_SEP}" & (sender of m) & "{FIELD_SEP}" & ((date received of m) as string) & "{RECORD_SEP}"
    set n to n + 1
  end repeat
end tell
return out
""".strip()
        code, stdout, stderr = self._run(script)
        if code != 0:
            if stderr.strip() == "__timeout__":
                raise MailError("La messagerie a mis trop de temps a repondre.", "mail_timeout")
            raise MailError(
                f"Lecture des mails impossible : {stderr.strip() or 'erreur AppleScript'}",
                "mail_read_failed",
            )

        emails = []
        for record in stdout.split(RECORD_SEP):
            record = record.strip()
            if not record:
                continue
            parts = record.split(FIELD_SEP)
            if len(parts) < 3:
                continue
            emails.append(
                {
                    "subject": parts[0].strip(),
                    "sender": parts[1].strip(),
                    "received": parts[2].strip(),
                }
            )
        return {"emails": emails, "unread_count": len(emails)}

    def create_draft(self, recipient: str, subject: str, body: str) -> dict[str, Any]:
        addr = recipient.replace('"', "'")
        subj = subject.replace('"', "'")
        content = body.replace('"', "'")
        script = f"""
tell application "Mail"
  set newMsg to make new outgoing message with properties {{subject:"{subj}", content:"{content}", visible:false}}
  tell newMsg
    make new to recipient with properties {{address:"{addr}"}}
    save
  end tell
end tell
return "ok"
""".strip()
        code, stdout, stderr = self._run(script)
        if code != 0 or "ok" not in stdout:
            if stderr.strip() == "__timeout__":
                raise MailError("La messagerie a mis trop de temps a repondre.", "mail_timeout")
            raise MailError(
                f"Creation du brouillon impossible : {stderr.strip() or 'erreur AppleScript'}",
                "mail_draft_failed",
            )
        return {
            "command_executed": True,
            "recipient": recipient,
            "subject": subject,
            "body_length": len(body),
        }

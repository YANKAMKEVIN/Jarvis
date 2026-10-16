"""Read and create events in Apple Calendar via AppleScript.

Local-first: drives Calendar.app with osascript (injectable for tests). Dates
are built from numeric components in AppleScript rather than parsed from a
string, which is locale-independent and reliable. Reading iterates calendars,
so it can be slow on large calendars -- callers keep it to a single day.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from typing import Any, Callable


# A runner takes AppleScript source and returns (returncode, stdout, stderr).
OsascriptRunner = Callable[[str], tuple[int, str, str]]

FIELD_SEP = "\u001f"   # unit separator, unlikely to appear in a title
RECORD_SEP = "\u001e"  # record separator


class CalendarError(Exception):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


# AppleScript reads of Calendar iterate events and can be slow; bound them so a
# voice tool never hangs, and surface a clear timeout instead.
DEFAULT_TIMEOUT_SECONDS = 12


def _default_runner(script: str) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=DEFAULT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return 1, "", "__timeout__"
    return completed.returncode, completed.stdout, completed.stderr


class CalendarTools:
    def __init__(self, runner: OsascriptRunner | None = None):
        self._run = runner if runner is not None else _default_runner

    def list_events_today(self, day_offset: int = 0) -> dict[str, Any]:
        offset = int(day_offset)
        script = f"""
set theDay to (current date)
set hours of theDay to 0
set minutes of theDay to 0
set seconds of theDay to 0
set theDay to theDay + ({offset} * days)
set nextDay to theDay + (1 * days)
set out to ""
tell application "Calendar"
  repeat with cal in calendars
    set evs to (every event of cal whose start date is greater than or equal to theDay and start date is less than nextDay)
    repeat with e in evs
      set out to out & (summary of e) & "{FIELD_SEP}" & ((start date of e) as string) & "{FIELD_SEP}" & ((end date of e) as string) & "{FIELD_SEP}" & (title of cal) & "{RECORD_SEP}"
    end repeat
  end repeat
end tell
return out
""".strip()
        code, stdout, stderr = self._run(script)
        if code != 0:
            if stderr.strip() == "__timeout__":
                raise CalendarError(
                    "L'agenda a mis trop de temps a repondre.", "calendar_timeout",
                )
            raise CalendarError(
                f"Lecture de l'agenda impossible : {stderr.strip() or 'erreur AppleScript'}",
                "calendar_read_failed",
            )

        events = []
        for record in stdout.split(RECORD_SEP):
            record = record.strip()
            if not record:
                continue
            parts = record.split(FIELD_SEP)
            if len(parts) < 4:
                continue
            events.append(
                {
                    "title": parts[0].strip(),
                    "start": parts[1].strip(),
                    "end": parts[2].strip(),
                    "calendar": parts[3].strip(),
                }
            )
        return {"day_offset": offset, "events": events, "event_count": len(events)}

    def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        calendar: str | None = None,
    ) -> dict[str, Any]:
        safe_title = title.replace('"', "'")
        target_calendar = (
            f'calendar "{calendar}"' if calendar else "first calendar whose writable is true"
        )
        script = f"""
set s to (current date)
set year of s to {start.year}
set month of s to {start.month}
set day of s to {start.day}
set hours of s to {start.hour}
set minutes of s to {start.minute}
set seconds of s to 0
set e to (current date)
set year of e to {end.year}
set month of e to {end.month}
set day of e to {end.day}
set hours of e to {end.hour}
set minutes of e to {end.minute}
set seconds of e to 0
tell application "Calendar"
  tell ({target_calendar})
    make new event with properties {{summary:"{safe_title}", start date:s, end date:e}}
  end tell
end tell
return "ok"
""".strip()
        code, stdout, stderr = self._run(script)
        if code != 0 or "ok" not in stdout:
            raise CalendarError(
                f"Creation de l'evenement impossible : {stderr.strip() or 'erreur AppleScript'}",
                "calendar_create_failed",
            )
        return {
            "command_executed": True,
            "title": title,
            "start": start.isoformat(timespec="minutes"),
            "end": end.isoformat(timespec="minutes"),
            "calendar": calendar,
        }

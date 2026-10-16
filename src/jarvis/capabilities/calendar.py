"""Apple Calendar: read today's events and create events (local, AppleScript)."""

from __future__ import annotations

from datetime import datetime

from jarvis.capabilities.results import ToolResult
from jarvis.tools.calendar import CalendarError, CalendarTools


class CalendarCapability:
    def __init__(self, calendar_tools: CalendarTools | None = None):
        self.calendar_tools = (
            calendar_tools if calendar_tools is not None else CalendarTools()
        )

    def list_today(self, day_offset: int = 0) -> ToolResult:
        try:
            state = self.calendar_tools.list_events_today(day_offset)
        except CalendarError as error:
            return self._failure("list_calendar_events", error)
        except Exception as error:
            return self._system_error("list_calendar_events", error)

        count = state.get("event_count", 0)
        if count:
            message = f"{count} evenement(s) dans l'agenda pour ce jour."
        else:
            message = "Aucun evenement dans l'agenda pour ce jour."
        return ToolResult.success(action="list_calendar_events", message=message, **state)

    def create_event(
        self,
        title: str,
        start: str,
        end: str,
        calendar: str | None = None,
    ) -> ToolResult:
        if not isinstance(title, str) or not title.strip():
            return ToolResult.failure(
                action="create_calendar_event",
                message="Le titre de l'evenement est obligatoire.",
                error_code="invalid_title",
            )
        try:
            start_dt = _parse_iso(start)
            end_dt = _parse_iso(end)
        except ValueError:
            return ToolResult.failure(
                action="create_calendar_event",
                message="Les dates doivent etre au format ISO 8601.",
                error_code="invalid_datetime",
            )
        if end_dt <= start_dt:
            return ToolResult.failure(
                action="create_calendar_event",
                message="La fin de l'evenement doit etre apres son debut.",
                error_code="invalid_range",
            )

        try:
            state = self.calendar_tools.create_event(title.strip(), start_dt, end_dt, calendar)
        except CalendarError as error:
            return self._failure("create_calendar_event", error)
        except Exception as error:
            return self._system_error("create_calendar_event", error)

        return ToolResult.success(
            action="create_calendar_event",
            message=f"Evenement « {title.strip()} » cree dans l'agenda.",
            **state,
        )

    @staticmethod
    def _failure(action: str, error: CalendarError) -> ToolResult:
        return ToolResult.failure(
            action=action, message=error.message, error_code=error.code or "calendar_error",
        )

    @staticmethod
    def _system_error(action: str, error: Exception) -> ToolResult:
        return ToolResult.failure(
            action=action, message=f"Echec de l'agenda : {error}", error_code="system_error",
        )


def _parse_iso(value: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)

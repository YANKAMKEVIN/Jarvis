"""Dictated notes: save spoken text to a Markdown file under the user's home.

Local and reliable. The "dictation" is just the text the voice model passes in;
this capability persists it to a dated file in a notes folder and can list the
recent notes. Writes stay inside the home folder.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

from jarvis.capabilities.results import ToolResult


MAX_TEXT_LENGTH = 20000
MAX_TITLE_LENGTH = 80


def default_notes_dir() -> Path:
    override = os.environ.get("JARVIS_NOTES_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Documents" / "Jarvis Notes"


class NotesCapability:
    def __init__(self, notes_dir: str | Path | None = None, clock=None):
        self._notes_dir = Path(notes_dir).expanduser() if notes_dir is not None else None
        self._clock = clock if clock is not None else datetime.now

    @property
    def notes_dir(self) -> Path:
        return self._notes_dir if self._notes_dir is not None else default_notes_dir()

    def save_note(self, text: str, title: str | None = None) -> ToolResult:
        if not isinstance(text, str) or not text.strip():
            return ToolResult.failure(
                action="save_note", message="La note est vide.", error_code="invalid_text",
            )
        if len(text) > MAX_TEXT_LENGTH:
            return ToolResult.failure(
                action="save_note", message="La note est trop longue.", error_code="invalid_text",
            )

        now = self._clock()
        stamp = now.strftime("%Y-%m-%d %H:%M")
        slug = _slug(title) if title else ""
        filename = f"{now.strftime('%Y%m%d-%H%M%S')}{('-' + slug) if slug else ''}.md"

        heading = title.strip() if isinstance(title, str) and title.strip() else "Note"
        body = f"# {heading}\n\n_{stamp}_\n\n{text.strip()}\n"

        try:
            directory = self.notes_dir
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / filename
            path.write_text(body, encoding="utf-8")
        except OSError as error:
            return ToolResult.failure(
                action="save_note", message=f"Ecriture de la note impossible : {error}",
                error_code="write_failed",
            )

        return ToolResult.success(
            action="save_note",
            message=f"Note enregistree ({path.name}).",
            path=str(path),
            title=heading,
            char_count=len(text.strip()),
        )

    def list_notes(self, limit: int = 10) -> ToolResult:
        directory = self.notes_dir
        if not directory.exists():
            return ToolResult.success(
                action="list_notes", message="Aucune note enregistree.", notes=[], count=0,
            )
        files = sorted(directory.glob("*.md"), key=lambda p: p.name, reverse=True)
        limit = max(1, min(int(limit), 100))
        notes = [{"name": f.name, "path": str(f)} for f in files[:limit]]
        return ToolResult.success(
            action="list_notes",
            message=f"{len(notes)} note(s) recente(s).",
            notes=notes,
            count=len(notes),
        )


def _slug(title: str) -> str:
    text = (title or "").strip().lower()[:MAX_TITLE_LENGTH]
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")

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
from threading import RLock
from uuid import uuid4

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
        self._lock = RLock()

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

        if title is not None and (not isinstance(title, str) or len(title) > MAX_TITLE_LENGTH or any(c in title for c in '\r\n')):
            return ToolResult.failure('save_note', 'Titre de note invalide.', 'invalid_title')
        now = self._clock()
        stamp = now.strftime("%Y-%m-%d %H:%M")
        slug = _slug(title) if title else ""
        filename = f"{now.strftime('%Y%m%d-%H%M%S')}{('-' + slug) if slug else ''}-{uuid4().hex[:8]}.md"

        heading = title.strip() if isinstance(title, str) and title.strip() else "Note"
        body = f"# {heading}\n\n_{stamp}_\n\n{text.strip()}\n"

        try:
            directory = self.notes_dir
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / filename
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                stream.write(body)
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

    def _resolve_note(self, note_id):
        if not isinstance(note_id, str) or Path(note_id).name != note_id or not note_id.endswith('.md') or '/' in note_id or '\\' in note_id:
            raise ValueError('invalid_note')
        path = self.notes_dir / note_id
        if path.is_symlink() or not path.is_file() or path.resolve().parent != self.notes_dir.resolve():
            raise ValueError('note_not_found')
        return path

    def read_note(self, note_id):
        try:
            with self._lock:
                path = self._resolve_note(note_id)
                if path.stat().st_size > 100000:
                    raise ValueError('note_too_large')
                text = path.read_text(encoding='utf-8')
            return ToolResult.success('read_note', text[:12000], note_id=note_id,
                                      text=text[:12000], truncated=len(text) > 12000)
        except (ValueError, OSError, UnicodeError):
            return ToolResult.failure('read_note', 'Note introuvable, invalide ou trop volumineuse.', 'note_unavailable')

    def search_notes(self, query):
        if not isinstance(query, str) or not query.strip() or len(query) > 200:
            return ToolResult.failure('search_notes', 'Recherche de note invalide.', 'invalid_query')
        matches = []
        try:
            files = sorted(self.notes_dir.glob('*.md'), reverse=True)[:200]
            for file in files:
                result = self.read_note(file.name)
                if result.ok and query.casefold() in (file.name + ' ' + result.data['text']).casefold():
                    matches.append({'note_id': file.name, 'title': (result.data['text'].splitlines() or [file.stem])[0].lstrip('# ')[:100]})
            return ToolResult.success('search_notes', f'{len(matches)} note(s) trouvee(s) dans les 200 notes recentes.',
                notes=matches[:20], count=len(matches), scanned=len(files), search_limited=True)
        except OSError:
            return ToolResult.failure('search_notes', 'Recherche de notes indisponible.', 'read_failed')

    def append_note(self, note_id, text):
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            return ToolResult.failure('append_note', 'Ajout de note invalide.', 'invalid_text')
        addition = ('\n\n' + text.strip() + '\n').encode('utf-8')
        try:
            with self._lock:
                path = self._resolve_note(note_id)
                if path.stat().st_size + len(addition) > 100000:
                    raise ValueError('note_too_large')
                descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | getattr(os, 'O_NOFOLLOW', 0))
                with os.fdopen(descriptor, 'ab') as stream:
                    stream.write(addition)
            return ToolResult.success('append_note', 'Texte ajoute a la note, contenu precedent conserve.',
                                      note_id=note_id, char_count=len(text.strip()), state_confirmed=True)
        except (ValueError, OSError):
            return ToolResult.failure('append_note', 'Ajout impossible. La note doit exister dans Jarvis Notes.', 'note_unavailable')


def _slug(title: str) -> str:
    text = (title or "").strip().lower()[:MAX_TITLE_LENGTH]
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


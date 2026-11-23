"""Export and import of the local memory as JSON (changing Mac, reinstalling).

The export holds profiles, people, preferences, facts and procedures, never
secrets (filtered at write time, checked again here). The import merges by
kind + subject: a new subject is added, an existing one takes the imported
content, an identical one is left alone. Every entry goes through the same
validation as a spoken « retiens ».
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from jarvis.memory.guard import contains_secret
from jarvis.memory.store import MemoryError, MemoryStore, subject_key

FORMAT = "jarvis-memory"
VERSION = 1
MAX_IMPORT_BYTES = 5 * 1024 * 1024


def export_memories(store: MemoryStore, now: float | None = None) -> dict[str, Any]:
    rows = [memory for memory in store.all_memories()
            if not contains_secret(memory.subject, memory.content)]
    return {
        "format": FORMAT, "version": VERSION,
        "exported_at": int(time.time() if now is None else now),
        "memories": [{"kind": m.kind, "subject": m.subject, "content": m.content, "source": m.source} for m in rows],
    }


def write_export(store: MemoryStore, path: Path) -> int:
    """Write the export atomically, owner-only (it is personal data)."""
    data = export_memories(store)
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".memoire-", suffix=".json")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return len(data["memories"])


def import_memories(store: MemoryStore, data: Any) -> dict[str, int]:
    if not isinstance(data, dict) or data.get("format") != FORMAT or data.get("version") != VERSION:
        raise MemoryError("Ce fichier n'est pas un export de mémoire Jarvis (version 1).", "invalid_import")
    entries = data.get("memories")
    if not isinstance(entries, list):
        raise MemoryError("Export de mémoire illisible : liste memories absente.", "invalid_import")
    counts = {"created": 0, "updated": 0, "unchanged": 0, "skipped": 0}
    existing = {(m.kind, subject_key(m.subject)): m for m in store.all_memories()}
    for entry in entries:
        try:
            if not isinstance(entry, dict):
                raise MemoryError("entree invalide", "invalid_import")
            kind, subject, content, source = MemoryStore.validate(
                entry.get("kind"), entry.get("subject"), entry.get("content"), entry.get("source", "user"))
        except MemoryError:
            counts["skipped"] += 1
            continue
        if contains_secret(subject, content):
            counts["skipped"] += 1
            continue
        current = existing.get((kind, subject_key(subject)))
        if current is not None and current.content == content:
            counts["unchanged"] += 1
            continue
        _, created = store.remember(kind, subject, content, source)
        counts["created" if created else "updated"] += 1
    return counts


def read_import(store: MemoryStore, path: Path) -> dict[str, int]:
    path = Path(path)
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise MemoryError("Fichier trop volumineux pour un export de mémoire.", "invalid_import")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise MemoryError("Fichier JSON illisible.", "invalid_import") from error
    return import_memories(store, data)

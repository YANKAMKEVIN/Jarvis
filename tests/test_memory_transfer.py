"""Export / import of the local memory as JSON (idea 44)."""
import json
import os
import stat

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from jarvis.memory.store import MemoryError, MemoryStore
from jarvis.memory.transfer import export_memories, import_memories, read_import, write_export


def store(tmp_path, name):
    return MemoryStore(path=tmp_path / name)


def test_round_trip_merges_by_kind_and_subject(tmp_path):
    old = store(tmp_path, "old.db")
    old.remember("person", "Ma mère", "Marie, sur WhatsApp")
    old.remember("preference", "Café", "Sans sucre")
    old.remember("procedure", "revue", "1. ouvrir Notes")
    path = tmp_path / "export.json"
    assert write_export(old, path) == 3
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    new = store(tmp_path, "new.db")
    new.remember("preference", "café", "Avec du lait")
    counts = read_import(new, path)
    assert counts == {"created": 2, "updated": 1, "unchanged": 0, "skipped": 0}
    assert new.find_by_subject("preference", "Café").content == "Sans sucre"
    assert read_import(new, path) == {"created": 0, "updated": 0, "unchanged": 3, "skipped": 0}


def test_secrets_and_invalid_entries_are_skipped(tmp_path):
    target = store(tmp_path, "m.db")
    data = {"format": "jarvis-memory", "version": 1, "memories": [
        {"kind": "fact", "subject": "Wifi", "content": "mot de passe : hunter2-Secret!-xx99"},
        {"kind": "unknown", "subject": "x", "content": "y"},
        "not a dict",
        {"kind": "fact", "subject": "Ville", "content": "Lyon"},
    ]}
    counts = import_memories(target, data)
    assert counts["created"] == 1 and counts["skipped"] == 3
    assert [m.subject for m in target.all_memories()] == ["Ville"]


def test_foreign_files_are_refused(tmp_path):
    target = store(tmp_path, "m.db")
    with pytest.raises(MemoryError):
        import_memories(target, {"format": "other"})
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    with pytest.raises(MemoryError):
        read_import(target, bad)
    assert export_memories(target)["memories"] == []


def test_editor_buttons_export_and_import(tmp_path):
    from PySide6.QtWidgets import QApplication
    from jarvis.context_store import ContextStore
    from jarvis.desktop.memory_editor import MemoryEditor
    QApplication.instance() or QApplication([])
    source = store(tmp_path, "a.db")
    source.remember("fact", "Ville", "Lyon")
    editor = MemoryEditor(memory=source, context=ContextStore(tmp_path / "c.db"))
    try:
        assert editor.export_file(str(tmp_path / "e.json")) == 1
        other = MemoryEditor(memory=store(tmp_path, "b.db"), context=ContextStore(tmp_path / "d.db"))
        assert other.import_file(str(tmp_path / "e.json"))["created"] == 1
        assert "1 ajouté" in other.status.text()
        other.close()
    finally:
        editor.close()
    assert json.loads((tmp_path / "e.json").read_text())["format"] == "jarvis-memory"

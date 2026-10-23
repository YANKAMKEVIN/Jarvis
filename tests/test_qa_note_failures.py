"""Storage failures must preserve files and return honest tool outcomes."""
import errno
from pathlib import Path
from unittest.mock import patch

import pytest
from jarvis.capabilities.notes import NotesCapability


@pytest.mark.parametrize('operation', ['save', 'append'])
def test_unencodable_text_is_rejected_without_creating_or_changing_a_note(tmp_path, operation):
    cap = NotesCapability(tmp_path)
    saved = cap.save_note('original', 'QA')
    assert saved.ok
    path = Path(saved.data['path'])
    before = path.read_bytes()
    before_files = set(tmp_path.iterdir())
    result = cap.save_note('broken \ud800 text', 'QA') if operation == 'save' else cap.append_note(path.name, 'broken \ud800 text')
    assert not result.ok
    assert result.error_code == 'invalid_text'
    assert path.read_bytes() == before
    assert set(tmp_path.iterdir()) == before_files


def test_unencodable_title_is_rejected_without_a_file(tmp_path):
    result = NotesCapability(tmp_path).save_note('QA', 'title\ud800')
    assert not result.ok and result.error_code == 'invalid_title'
    assert list(tmp_path.iterdir()) == []


def test_failed_save_removes_its_partial_file(tmp_path):
    import os
    fdopen = os.fdopen
    class DiskFull:
        def __init__(self, *args, **kwargs):
            self.stream = fdopen(*args, **kwargs)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            self.stream.close()
        def write(self, content):
            self.stream.write(content[:10])
            self.stream.flush()
            raise OSError(errno.ENOSPC, 'simulated full disk')
    with patch('jarvis.capabilities.notes.os.fdopen', DiskFull):
        result = NotesCapability(tmp_path).save_note('QA complete content', 'QA')
    assert not result.ok and result.error_code == 'write_failed'
    assert list(tmp_path.iterdir()) == []


def test_failed_creation_never_removes_an_existing_file(tmp_path):
    from datetime import datetime
    from types import SimpleNamespace
    cap = NotesCapability(tmp_path, clock=lambda: datetime(2026,10,23,12,0))
    with patch('jarvis.capabilities.notes.uuid4', return_value=SimpleNamespace(hex='a'*32)):
        saved = cap.save_note('precious original', 'QA')
        assert saved.ok
        existing = Path(saved.data['path'])
        before = existing.read_bytes()
        result = cap.save_note('replacement', 'QA')  # Real O_EXCL collision.
    assert not result.ok
    assert existing.read_bytes() == before
    assert list(tmp_path.iterdir()) == [existing]


def test_failed_append_rolls_back_partial_addition(tmp_path):
    import os
    cap = NotesCapability(tmp_path)
    path = Path(cap.save_note('original', 'QA').data['path'])
    before = path.read_bytes()
    write = os.write
    attempts = []
    def disk_full(fd, content):
        if not attempts:
            attempts.append(1)
            return write(fd, content[:3])
        raise OSError(errno.ENOSPC, 'simulated full disk')
    with patch('jarvis.capabilities.notes.os.write', disk_full):
        result = cap.append_note(path.name, 'complete addition')
    assert not result.ok
    assert path.read_bytes() == before


def test_short_writes_are_completed_without_truncation(tmp_path):
    import os
    cap = NotesCapability(tmp_path)
    path = Path(cap.save_note('original', 'QA').data['path'])
    write = os.write
    with patch('jarvis.capabilities.notes.os.write', lambda fd, content: write(fd, content[:2])):
        result = cap.append_note(path.name, 'complete addition')
    assert result.ok
    assert path.read_text().endswith('\n\ncomplete addition\n')


def test_independent_note_instances_preserve_every_concurrent_append(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    cap = NotesCapability(tmp_path)
    path = Path(cap.save_note('original', 'QA').data['path'])
    def append(i):
        return NotesCapability(tmp_path).append_note(path.name, f'qa-token-{i}')
    with ThreadPoolExecutor(8) as pool:
        assert all(result.ok for result in pool.map(append, range(100)))
    tokens = [line for line in path.read_text().splitlines() if line.startswith('qa-token-')]
    assert sorted(tokens) == sorted(f'qa-token-{i}' for i in range(100))

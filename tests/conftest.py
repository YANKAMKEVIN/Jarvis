import os
import tempfile
from pathlib import Path

from jarvis.memory import store as memory_store

# Default stores and transcript discovery belong to a disposable test directory,
# never the user's ~/Library/Application Support/Jarvis or Claude history.
# Individual tests can still provide their own explicit paths.
# Any MemoryStore built with
# the default path resolves it through default_memory_path() at use time, so
# pin that to a throwaway file. Patching the function (not only the env var)
# keeps tests that clear os.environ isolated too.
_TEST_DATA = tempfile.TemporaryDirectory(prefix="jarvis-test-data-")
_TEST_ROOT = Path(_TEST_DATA.name)
for variable, name in {
    "JARVIS_MEMORY_PATH": "memory.db",
    "JARVIS_SCHEDULE_PATH": "scheduled.db",
    "JARVIS_REMINDERS_PATH": "reminders.db",
    "JARVIS_CONTEXT_PATH": "context.db",
    "JARVIS_MACROS_PATH": "macros.db",
    "JARVIS_CHECKLISTS_PATH": "checklists.db",
    "JARVIS_RESULT_HISTORY_PATH": "results.db",
    "JARVIS_METRICS_DB_PATH": "metrics.db",
    "JARVIS_USAGE_DB_PATH": "usage.db",
    "JARVIS_ACTIVITY_DB_PATH": "activity.db",
    "JARVIS_CLAUDE_PROJECTS_DIR": "claude-projects",
    "JARVIS_NOTES_DIR": "notes",
    "JARVIS_INTRODUCED_PATH": "introduced",
}.items():
    os.environ[variable] = str(_TEST_ROOT / name)
_MEMORY_PATH = _TEST_ROOT / "memory.db"
# Every tool call would otherwise land in the activity journal and skew the
# counts other tests assert; tests/test_activity.py turns it back on.
os.environ["JARVIS_ACTIVITY_DISABLED"] = "1"

memory_store.real_default_memory_path = memory_store.default_memory_path
memory_store.default_memory_path = lambda: _MEMORY_PATH

# Same for the activity journal: tests that clear os.environ also drop
# JARVIS_ACTIVITY_DISABLED, and must still never reach the real file.
from jarvis import activity as activity_journal

activity_journal.default_activity_db_path = lambda: _TEST_ROOT / "activity.db"


# GUI fixtures used to leave hidden top-level windows and deferred deletions
# alive across cases. Global stylesheet changes then repolished every old
# window, making the suite order-dependent and progressively slower.
import sys
import pytest


@pytest.fixture(autouse=True)
def dispose_test_windows():
    widgets = sys.modules.get('PySide6.QtWidgets')
    app = widgets.QApplication.instance() if widgets else None
    existing_windows = tuple(app.topLevelWidgets()) if app else ()
    existing = {id(window) for window in existing_windows}
    previous_experience = getattr(app, '_jarvis_experience', None) if app else None
    yield
    widgets = sys.modules.get('PySide6.QtWidgets')
    app = widgets.QApplication.instance() if widgets else None
    if app is None:
        return
    from PySide6.QtCore import QCoreApplication, QEvent
    experience = getattr(app, '_jarvis_experience', None)
    if experience is not None and experience is not previous_experience:
        experience.close()
        app._jarvis_experience = None
    for window in app.topLevelWidgets():
        if id(window) not in existing:
            window.hide()
            window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

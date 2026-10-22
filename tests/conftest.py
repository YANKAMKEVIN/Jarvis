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
    "JARVIS_CLAUDE_PROJECTS_DIR": "claude-projects",
    "JARVIS_NOTES_DIR": "notes",
}.items():
    os.environ[variable] = str(_TEST_ROOT / name)
_MEMORY_PATH = _TEST_ROOT / "memory.db"

memory_store.real_default_memory_path = memory_store.default_memory_path
memory_store.default_memory_path = lambda: _MEMORY_PATH

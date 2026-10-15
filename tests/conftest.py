import os
import tempfile
from pathlib import Path

from jarvis.memory import store as memory_store

# Tests must never read or write the user's real long-term memory
# (~/Library/Application Support/Jarvis/memory.db). Any MemoryStore built with
# the default path resolves it through default_memory_path() at use time, so
# pin that to a throwaway file. Patching the function (not only the env var)
# keeps tests that clear os.environ isolated too.
_MEMORY_PATH = Path(tempfile.mkdtemp(prefix="jarvis-test-memory-")) / "memory.db"
os.environ["JARVIS_MEMORY_PATH"] = str(_MEMORY_PATH)

memory_store.real_default_memory_path = memory_store.default_memory_path
memory_store.default_memory_path = lambda: _MEMORY_PATH

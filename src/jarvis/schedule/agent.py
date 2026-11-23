"""Is the launchd agent that delivers scheduled messages and reminders installed?

schedule_message and set_reminder only write to the local database; the
`com.jarvis.scheduler` agent (``python -m jarvis.schedule install``) is what
delivers them every minute. Without it, nothing would ever leave, silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

LAUNCHD_LABEL = "com.jarvis.scheduler"
INSTALL_HINT = "python -m jarvis.schedule install"
MISSING_MESSAGE = (
    "Attention : l'agent d'envoi programmé n'est pas installé sur ce Mac, "
    "rien ne partira à l'heure prévue tant qu'il manque. "
    f"Pour l'installer : {INSTALL_HINT} (Tableau de bord, onglet Jarvis)."
)


def agent_plist_path(home: Path | None = None) -> Path:
    base = Path.home() if home is None else Path(home)
    return base / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def scheduler_agent_status(home: Path | None = None, platform: str | None = None) -> str:
    """'installed', 'missing', or 'unsupported' off macOS (no launchd)."""
    if (platform or sys.platform) != "darwin":
        return "unsupported"
    try:
        return "installed" if agent_plist_path(home).is_file() else "missing"
    except OSError:
        return "missing"


def scheduler_agent_missing(home: Path | None = None, platform: str | None = None) -> bool:
    return scheduler_agent_status(home, platform) == "missing"

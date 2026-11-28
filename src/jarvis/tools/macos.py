"""macOS primitives: applications, URLs, date and volume.

MacOSTools also composes the window, media and system groups, so every
caller keeps using a single MacOSTools object.
"""
import subprocess
import time  # noqa: F401 -- tests patch jarvis.tools.macos.time.sleep
import urllib.parse
import webbrowser
from datetime import datetime

from jarvis.tools.macos_base import (
    SUPPORTED_MEDIA_APPS,
    MEDIA_OBSERVATION_ATTEMPTS,
    MEDIA_OBSERVATION_INTERVAL_SECONDS,
    WINDOW_GEOMETRY_TOLERANCE_PIXELS,
    WINDOW_DEFAULT_MENU_BAR_OFFSET,
    WINDOW_STATE_OBSERVATION_ATTEMPTS,
    WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS,
    WINDOW_FULLSCREEN_TRANSITION_ATTEMPTS,
    WINDOW_READY_STABLE_OBSERVATIONS,
    WINDOW_RECORD_SEPARATOR,
    AppleScriptRunner,
)
from jarvis.tools.macos_system import SystemToolsMixin
from jarvis.tools.macos_media import MediaToolsMixin
from jarvis.tools.macos_window_actions import WindowActionsMixin
from jarvis.tools.macos_window_state import WindowStateMixin
from jarvis.tools.macos_window_geometry import WindowGeometryMixin

__all__ = [
    "MacOSTools",
    "SUPPORTED_MEDIA_APPS",
    "MEDIA_OBSERVATION_ATTEMPTS",
    "MEDIA_OBSERVATION_INTERVAL_SECONDS",
    "WINDOW_GEOMETRY_TOLERANCE_PIXELS",
    "WINDOW_DEFAULT_MENU_BAR_OFFSET",
    "WINDOW_STATE_OBSERVATION_ATTEMPTS",
    "WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS",
    "WINDOW_FULLSCREEN_TRANSITION_ATTEMPTS",
    "WINDOW_READY_STABLE_OBSERVATIONS",
    "WINDOW_RECORD_SEPARATOR",
]


class MacOSTools(
    SystemToolsMixin,
    MediaToolsMixin,
    WindowActionsMixin,
    WindowStateMixin,
    WindowGeometryMixin,
    AppleScriptRunner,
):
    def open_app(self, app_name: str) -> str:
        if not app_name or not app_name.strip():
            raise ValueError("Nom d'application manquant.")

        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return f"{app_name} a ete ouvert."

    def close_app(self, app_name: str) -> str:
        if not app_name or not app_name.strip():
            raise ValueError("Nom d'application manquant.")

        safe_name = app_name.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "{safe_name}" to quit'

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return f"{app_name} a ete ferme."

    def is_app_running(self, app_name: str) -> bool:
        if not app_name or not app_name.strip():
            raise ValueError("Nom d'application manquant.")

        safe_name = app_name.replace("\\", "\\\\").replace('"', '\\"')
        script = f'application "{safe_name}" is running'

        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return result.stdout.strip().lower() == "true"

    def open_url(self, url: str) -> str:
        if not url or not url.strip():
            raise ValueError("URL manquante.")

        url = url.strip()

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        webbrowser.open(url)
        return f"J'ai ouvert {url}."

    def web_search(self, query: str) -> str:
        if not query or not query.strip():
            raise ValueError("Recherche manquante.")

        encoded_query = urllib.parse.quote_plus(query.strip())
        url = f"https://www.google.com/search?q={encoded_query}"

        webbrowser.open(url)
        return f"Recherche lancee pour : {query}."

    def get_date(self) -> str:
        return datetime.now().strftime("%d/%m/%Y")

    def set_volume(self, level: int) -> str:
        level = int(level)

        if not 0 <= level <= 100:
            raise ValueError("Le volume doit etre compris entre 0 et 100.")

        script = f"set volume output volume {level}"

        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return f"Volume regle a {level} %."

    def get_volume(self) -> int:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                "output volume of (get volume settings)",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return int(result.stdout.strip())

    def mute(self) -> str:
        subprocess.run(
            ["osascript", "-e", "set volume output muted true"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return "Son coupe."

    def unmute(self) -> str:
        subprocess.run(
            ["osascript", "-e", "set volume output muted false"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return "Son reactive."

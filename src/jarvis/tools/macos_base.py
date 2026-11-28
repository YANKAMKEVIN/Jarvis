"""AppleScript/JXA execution and parsing shared by every macOS tool group."""
import subprocess


SUPPORTED_MEDIA_APPS = ("Music", "Spotify")
MEDIA_OBSERVATION_ATTEMPTS = 3
MEDIA_OBSERVATION_INTERVAL_SECONDS = 0.15
WINDOW_GEOMETRY_TOLERANCE_PIXELS = 8
WINDOW_DEFAULT_MENU_BAR_OFFSET = 25
WINDOW_STATE_OBSERVATION_ATTEMPTS = 3
WINDOW_STATE_OBSERVATION_INTERVAL_SECONDS = 0.15
WINDOW_FULLSCREEN_TRANSITION_ATTEMPTS = 8
WINDOW_READY_STABLE_OBSERVATIONS = 2
WINDOW_RECORD_SEPARATOR = "__JARVIS_WINDOW__"


class AppleScriptRunner:
    """AppleScript/JXA execution and parsing shared by every macOS tool group. Mixed into MacOSTools."""

    @staticmethod
    def _parse_applescript_bool(value: str) -> bool:
        return value.strip().lower() == "true"

    @staticmethod
    def _escape_applescript(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _run_osascript(script: str):
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return result

    @staticmethod
    def _run_osa_javascript(script: str):
        result = subprocess.run(
            ["osascript", "-l", "JavaScript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            error = result.stderr.strip() or "Erreur macOS inconnue."
            raise RuntimeError(error)

        return result

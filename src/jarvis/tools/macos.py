import subprocess
import time
import urllib.parse
import webbrowser
from datetime import datetime


SUPPORTED_MEDIA_APPS = ("Music", "Spotify")
MEDIA_OBSERVATION_ATTEMPTS = 3
MEDIA_OBSERVATION_INTERVAL_SECONDS = 0.15


class MacOSTools:
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

    def play_pause(self) -> dict:
        app_name = self._active_media_app()

        if app_name is None:
            raise RuntimeError("Aucune application media compatible active.")

        self._run_osascript(
            f'tell application "{self._escape_applescript(app_name)}" to playpause'
        )
        state = self.get_media_state(app_name)
        state["app"] = app_name

        return state

    def next_track(self) -> dict:
        app_name, before_state = self._active_media_context()

        if app_name is None:
            raise RuntimeError("Aucune application media compatible active.")

        self._run_osascript(
            f'tell application "{self._escape_applescript(app_name)}" to next track'
        )
        state = self._media_state_after_command(
            app_name,
            before_state,
            command_attempts=1,
        )

        return state

    def previous_track(self) -> dict:
        app_name, before_state = self._active_media_context()

        if app_name is None:
            raise RuntimeError("Aucune application media compatible active.")

        self._run_osascript(
            f'tell application "{self._escape_applescript(app_name)}" to previous track'
        )
        state = self._media_state_after_command(
            app_name,
            before_state,
            command_attempts=1,
        )

        if state["track_changed"]:
            return state

        if not state["command_executed"] or not state["media_observed"]:
            return state

        self._run_osascript(
            f'tell application "{self._escape_applescript(app_name)}" to previous track'
        )
        state = self._media_state_after_command(
            app_name,
            state,
            command_attempts=2,
        )

        return state

    def get_media_state(self, app_name: str | None = None) -> dict:
        if app_name is None:
            app_name, state = self._active_media_context()

            if app_name is not None:
                return state

        if app_name is None:
            return {
                "media_available": False,
                "playing": False,
                "title": None,
                "artist": None,
                "app": None,
            }

        safe_name = self._escape_applescript(app_name)
        script = "\n".join([
            f'tell application "{safe_name}"',
            'set track_name to ""',
            'set artist_name to ""',
            "try",
            "set track_name to name of current track",
            "end try",
            "try",
            "set artist_name to artist of current track",
            "end try",
            "set playback_state to player state as text",
            "return playback_state & linefeed & track_name & linefeed & artist_name",
            "end tell",
        ])
        output = self._run_osascript(script).stdout.splitlines()
        playback_state = output[0].strip().lower() if output else ""
        title = output[1].strip() if len(output) > 1 and output[1].strip() else None
        artist = output[2].strip() if len(output) > 2 and output[2].strip() else None
        media_available = bool(playback_state or title or artist)

        return {
            "media_available": media_available,
            "playing": playback_state == "playing",
            "title": title,
            "artist": artist,
            "app": app_name,
        }

    def _active_media_app(self) -> str | None:
        app_name, _state = self._active_media_context()
        return app_name

    def _active_media_context(self) -> tuple[str | None, dict | None]:
        for app_name in SUPPORTED_MEDIA_APPS:
            if not self.is_app_running(app_name):
                continue

            try:
                state = self.get_media_state(app_name)
            except Exception:
                continue

            if state["media_available"]:
                return app_name, state

        return None, None

    def _media_state_after_command(
        self,
        app_name: str,
        before_state: dict | None,
        command_attempts: int,
    ) -> dict:
        before_title = before_state.get("title") if before_state else None
        before_artist = before_state.get("artist") if before_state else None
        after_state = None
        attempts = 0

        for attempt in range(1, MEDIA_OBSERVATION_ATTEMPTS + 1):
            attempts = attempt
            after_state = self.get_media_state(app_name)
            after_title = after_state.get("title")
            after_artist = after_state.get("artist")
            track_changed = after_state.get("media_available", False) and (
                (before_title, before_artist) != (after_title, after_artist)
            )

            if track_changed or not after_state.get("media_available", False):
                break

            if attempt < MEDIA_OBSERVATION_ATTEMPTS:
                time.sleep(MEDIA_OBSERVATION_INTERVAL_SECONDS)

        if after_state is None:
            after_state = {
                "media_available": False,
                "playing": False,
                "title": None,
                "artist": None,
                "app": app_name,
            }

        after_state["app"] = app_name
        after_state["command_executed"] = True
        after_state["media_observed"] = after_state.get("media_available", False)
        after_title = after_state.get("title")
        after_artist = after_state.get("artist")
        after_state["previous_title"] = before_title
        after_state["previous_artist"] = before_artist
        after_state["track_changed"] = after_state["media_observed"] and (
            (before_title, before_artist) != (after_title, after_artist)
        )
        after_state["observation_attempts"] = attempts
        after_state["command_attempts"] = command_attempts

        return after_state

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

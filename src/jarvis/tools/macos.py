import subprocess
import urllib.parse
import webbrowser
from datetime import datetime


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

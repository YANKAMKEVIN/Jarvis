import subprocess


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

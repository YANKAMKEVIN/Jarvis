"""One version, read from pyproject.toml everywhere (idea 27)."""
import importlib.util
import tomllib
from pathlib import Path

from jarvis.capabilities.diagnostics import DiagnosticsCapability
from jarvis.version import jarvis_version

ROOT = Path(__file__).resolve().parents[1]
DECLARED = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_version_matches_pyproject():
    assert jarvis_version() == DECLARED


def test_launcher_and_self_check_use_it(tmp_path):
    spec = importlib.util.spec_from_file_location("launcher", ROOT / "scripts/build_desktop_app.py")
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    import plistlib
    app = launcher.build_app(tmp_path / "Jarvis.app", Path("/python"), tmp_path)
    with (app / "Contents/Info.plist").open("rb") as stream:
        assert plistlib.load(stream)["CFBundleShortVersionString"] == DECLARED
    result = DiagnosticsCapability(checks={"ok": lambda: (True, "ok")}).self_check()
    assert result.data["version"] == DECLARED and DECLARED in result.message
    assert '"0.9.0"' not in (ROOT / "scripts/build_desktop_app.py").read_text()


def test_readme_states_the_same_version():
    assert f"**{DECLARED}**" in (ROOT / "README.md").read_text()

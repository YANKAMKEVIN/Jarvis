import importlib.util
from pathlib import Path
import plistlib
import subprocess

import pytest

spec = importlib.util.spec_from_file_location("desktop_launcher", Path(__file__).parents[1] / "scripts/build_desktop_app.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_launcher_quotes_paths_and_never_overwrites(tmp_path):
    # Validate the generated script by executing a fake interpreter: paths with
    # spaces, apostrophes and dollar signs must survive shell parsing unchanged.
    python = tmp_path / "python's environment $literal" / "python"
    python.parent.mkdir()
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$PYTHONPATH" "$@"\n')
    python.chmod(0o755)
    source = tmp_path / "source's folder $literal"
    app = launcher.build_app(tmp_path / "Jarvis.app", python, source, demo=True)
    result = subprocess.run([str(app / "Contents/MacOS/Jarvis"), "--compact"], capture_output=True, text=True, check=True)
    assert result.stdout.splitlines() == [str(source.resolve()), "-m", "jarvis.desktop", "--demo", "--compact"]
    with (app / "Contents/Info.plist").open("rb") as stream:
        assert plistlib.load(stream)["CFBundleExecutable"] == "Jarvis"
    with pytest.raises(FileExistsError):
        launcher.build_app(app, python, source)
    with pytest.raises(ValueError):
        launcher.build_app(tmp_path / "not-an-app", python, source)

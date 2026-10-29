import importlib.util
from pathlib import Path
import plistlib
import subprocess
import sys

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


def test_update_keeps_resources_and_adds_microphone_permission(tmp_path):
    app = launcher.build_app(tmp_path / "Jarvis.app", Path('/python'), tmp_path)
    marker = app / "Contents/Resources/my-file"
    marker.parent.mkdir()
    marker.write_text("keep")
    launcher.build_app(app, Path('/new-python'), tmp_path, update=True)
    assert marker.read_text() == "keep"
    with (app / "Contents/Info.plist").open('rb') as stream:
        info = plistlib.load(stream)
    # Usage descriptions so a real .app can actually prompt for these grants.
    for key in ("NSMicrophoneUsageDescription", "NSCalendarsUsageDescription",
                "NSRemindersUsageDescription", "NSAppleEventsUsageDescription",
                "NSCameraUsageDescription"):
        assert key in info, key
    assert info["LSUIElement"] is True  # menu-bar/orb app, no Dock icon
    info_path = app / "Contents/Info.plist"
    with info_path.open('wb') as stream:
        plistlib.dump({"CFBundleIdentifier": "another.application"}, stream)
    with pytest.raises(ValueError):
        launcher.build_app(app, Path('/python'), tmp_path, update=True)


def test_sign_app_is_best_effort_without_codesign(tmp_path, monkeypatch):
    # On a host without codesign, signing must not raise and must not fail the
    # build; it reports a warning instead.
    app = launcher.build_app(tmp_path / "Jarvis.app", Path('/python'), tmp_path)

    def no_codesign(*args, **kwargs):
        raise FileNotFoundError("codesign")

    monkeypatch.setattr(launcher.subprocess, "run", no_codesign)
    ok, detail = launcher.sign_app(app)
    assert ok is False
    assert "codesign" in detail


@pytest.mark.skipif(sys.platform != "darwin", reason="codesign only exists on macOS")
def test_sign_app_adhoc_signs_and_is_stable_across_rebuilds(tmp_path):
    # Real ad-hoc signature: it must verify, and rebuilding the same launcher
    # must yield the same code hash so macOS keeps the TCC grants.
    app = launcher.build_app(tmp_path / "Jarvis.app", Path(sys.executable), tmp_path)
    ok, detail = launcher.sign_app(app)
    assert ok is True and detail == "ad-hoc"
    assert subprocess.run(["codesign", "--verify", "--strict", str(app)]).returncode == 0

    def cdhash() -> str:
        out = subprocess.run(["codesign", "-dvvv", str(app)], capture_output=True, text=True)
        line = next(l for l in (out.stderr + out.stdout).splitlines() if l.startswith("CDHash="))
        return line.split("=", 1)[1]

    first = cdhash()
    launcher.build_app(app, Path(sys.executable), tmp_path, update=True)
    launcher.sign_app(app)
    assert cdhash() == first

"""CI preview: every desktop page captured offscreen, docs/ untouched (idea 48)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("capture_all", ROOT / "scripts/capture_all.py")
capture_all = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture_all)


def test_menu_capture_goes_to_the_requested_folder(tmp_path, monkeypatch):
    docs_png = ROOT / "docs/screenshots/menu-controls.png"
    before = docs_png.stat().st_mtime if docs_png.exists() else None
    monkeypatch.setattr(capture_all, "SCRIPTS", (("capture_desktop_menu.py", []),))
    assert capture_all.main(["--output", str(tmp_path)]) == 0
    assert (tmp_path / "menu-controls.png").stat().st_size > 1000
    assert (docs_png.stat().st_mtime if docs_png.exists() else None) == before


def test_ci_runs_and_publishes_the_captures():
    workflow = (ROOT / ".github/workflows/tests.yml").read_text()
    assert "scripts/capture_all.py --output captures" in workflow and "name: desktop-captures" in workflow

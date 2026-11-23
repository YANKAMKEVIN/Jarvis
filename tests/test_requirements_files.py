"""requirements-*.txt never contradict pyproject.toml (idea 19)."""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def specs():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    out = {}
    for extra in data["project"]["optional-dependencies"].values():
        for requirement in extra:
            name = re.split(r"[\[<>=~!;\s]", requirement, maxsplit=1)[0].lower()
            out[name] = requirement.split(";")[0].replace(name, "", 1).strip()
            out[name] = re.sub(r"^\[[^\]]*\]", "", out[name])
    return out


def test_requirement_files_point_to_extras_and_agree_on_versions():
    declared = specs()
    for path in ROOT.glob("requirements-*.txt"):
        lines = [line.split("#")[0].strip() for line in path.read_text().splitlines()]
        lines = [line for line in lines if line]
        assert any(line.startswith("-e .[") for line in lines), path.name
        for line in lines:
            if line.startswith("-e "):
                continue
            name = re.split(r"[\[<>=~!;\s]", line, maxsplit=1)[0].lower()
            if name in declared:
                spec = re.sub(r"^\[[^\]]*\]", "", line.split(";")[0][len(name):]).strip()
                assert spec.replace(" ", "") == declared[name].replace(" ", ""), (path.name, line, declared[name])

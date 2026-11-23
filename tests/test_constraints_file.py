"""constraints.txt pins one tested resolution inside pyproject's ranges (idea 20)."""
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def pins():
    out = {}
    for line in (ROOT / "constraints.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if line:
            name, version = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([^\s;]+)", line).groups()
            out[canonicalize_name(name)] = version
    return out


def test_every_pin_is_exact_and_inside_the_declared_range():
    pinned = pins()
    assert pinned, "constraints.txt is empty"
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    checked = 0
    for extra in ("desktop", "live", "test", "mcp"):
        for raw in data["project"]["optional-dependencies"][extra]:
            requirement = Requirement(raw)
            name = canonicalize_name(requirement.name)
            if name in pinned:
                assert requirement.specifier.contains(pinned[name], prereleases=True), (raw, pinned[name])
                checked += 1
    assert checked >= 8


def test_ci_installs_with_the_constraints():
    workflow = (ROOT / ".github/workflows/tests.yml").read_text()
    assert workflow.count("-c constraints.txt") >= 2

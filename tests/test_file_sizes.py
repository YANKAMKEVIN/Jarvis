"""The file-size guard (scripts/check_file_sizes.py) holds and behaves as documented."""
import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_file_sizes.py"
_spec = importlib.util.spec_from_file_location("check_file_sizes", _SCRIPT)
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def test_repository_respects_file_size_budget():
    assert guard.violations(guard.line_counts()) == []


def test_new_oversize_file_is_rejected():
    problems = guard.violations({"src/new.py": 401}, allowed={}, limit=400)
    assert problems and "src/new.py" in problems[0]


def test_listed_file_cannot_grow():
    problems = guard.violations({"src/big.py": 501}, allowed={"src/big.py": 500}, limit=400)
    assert problems and "must not grow" in problems[0]


def test_ceiling_must_follow_a_shrink():
    problems = guard.violations({"src/big.py": 450}, allowed={"src/big.py": 500}, limit=400)
    assert problems and "lower its ceiling" in problems[0]


def test_file_back_under_limit_must_leave_the_list():
    problems = guard.violations({"src/big.py": 380}, allowed={"src/big.py": 500}, limit=400)
    assert problems and "remove it" in problems[0]


def test_vanished_listed_file_is_reported():
    problems = guard.violations({}, allowed={"src/gone.py": 500}, limit=400)
    assert problems and "no longer exists" in problems[0]


def test_exact_ceiling_and_small_files_pass():
    assert guard.violations({"src/big.py": 500, "src/ok.py": 400},
                            allowed={"src/big.py": 500}, limit=400) == []

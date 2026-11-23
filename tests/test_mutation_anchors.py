"""Every targeted mutation still finds its anchor, before the slow CI step does."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sensitivity", ROOT / "scripts/check_regression_sensitivity.py")
sensitivity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sensitivity)


@pytest.mark.parametrize("mutation", sensitivity.MUTATIONS, ids=[m[0] for m in sensitivity.MUTATIONS])
def test_anchor_is_unique_and_target_exists(mutation):
    name, path, before, after, target = mutation
    source = (ROOT / "src" / path).read_text()
    assert source.count(before) == 1, f"Mutation anchor changed: {name} (update scripts/check_regression_sensitivity.py)"
    assert before != after
    assert (ROOT / target.split("::")[0]).is_file()


def test_november_protections_are_covered():
    names = {m[0] for m in sensitivity.MUTATIONS}
    assert {"confirmation_without_user_turn", "executable_open_allowed", "ssh_folder_readable",
            "local_url_summarized", "mcp_call_allowed_in_safe_mode"} <= names

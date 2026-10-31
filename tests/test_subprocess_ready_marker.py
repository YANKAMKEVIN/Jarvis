"""The start-up ceiling must never hide a hang in the timed phase."""
import subprocess
import sys
import time

import pytest


def test_hang_after_marker_still_hits_the_strict_timeout(run_after_ready):
    code = 'import time\nprint("IMPORTS_DONE", flush=True)\ntime.sleep(60)'
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        run_after_ready([sys.executable, '-c', code], env=None, marker='IMPORTS_DONE', timeout=1)
    assert time.monotonic() - started < 30


def test_hang_before_marker_hits_the_startup_ceiling(run_after_ready):
    code = 'import time\ntime.sleep(60)'
    with pytest.raises(subprocess.TimeoutExpired):
        run_after_ready([sys.executable, '-c', code], env=None, marker='IMPORTS_DONE',
                        timeout=1, startup_timeout=1)


def test_child_that_fails_before_marker_reports_its_error(run_after_ready):
    code = 'import sys\nprint("partial")\nsys.exit("boom")'
    result = run_after_ready([sys.executable, '-c', code], env=None, marker='IMPORTS_DONE', timeout=1)
    assert result.returncode == 1
    assert 'partial' in result.stdout
    assert 'boom' in result.stderr

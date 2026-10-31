"""Exercise a real SIGINT in a separate Qt event loop, without macOS tools."""
import os
from pathlib import Path
import sys

import pytest
pytest.importorskip("PySide6")


def test_ctrl_c_exits_even_with_reduced_motion(run_after_ready):
    source = Path(__file__).parents[1] / "src"
    code = '''
import os
import signal
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from jarvis.desktop.app import run, DesktopShell
app = QApplication([])
# Stop all decorative animation timers: SIGINT must not depend on the orb.
original = DesktopShell.show_full
def show_static(self):
    self.controller.reduced_motion = True
    self.controller.changed.emit()
    original(self)
DesktopShell.show_full = show_static
previous = signal.getsignal(signal.SIGINT)
print("IMPORTS_DONE", flush=True)
QTimer.singleShot(100, lambda: os.kill(os.getpid(), signal.SIGINT))
assert run(demo=True) == 0
assert signal.getsignal(signal.SIGINT) is previous
print("EXITED_CLEANLY")
'''
    result = run_after_ready(
        [sys.executable, "-c", code],
        env={**os.environ, "PYTHONPATH": str(source), "QT_QPA_PLATFORM": "offscreen"},
        marker="IMPORTS_DONE", timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "EXITED_CLEANLY" in result.stdout
    assert "KeyboardInterrupt" not in result.stderr
    assert "Traceback" not in result.stderr

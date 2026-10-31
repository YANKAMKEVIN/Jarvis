"""Test offline setup in a real Qt worker, without importing Live/audio SDKs."""
import os
from pathlib import Path
import sys
import pytest
pytest.importorskip('PySide6')


def test_diagnostic_runs_in_background_thread_with_asyncio_loop(run_after_ready):
    script = Path(__file__).parents[1] / 'scripts/diagnose_desktop_voice.py'
    code = '''
import asyncio, importlib.util, sys, threading
spec = importlib.util.spec_from_file_location('diagnostic', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print('IMPORTS_DONE', flush=True)
async def check():
    assert threading.current_thread() is not threading.main_thread()
    assert asyncio.get_running_loop().is_running()
    print('WORKER_CONTEXT_OK')
    return 7
assert module.run_in_worker(check) == 7
'''
    result = run_after_ready([sys.executable, '-c', code, str(script)],
        env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
        marker='IMPORTS_DONE', timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'WORKER_CONTEXT_OK' in result.stdout


def test_real_google_plugin_preloads_on_main_before_worker_model_construction(run_after_ready):
    pytest.importorskip('livekit.plugins.google')
    source = Path(__file__).parents[1] / 'src'
    code = '''
import asyncio, os, threading
from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication
from jarvis.desktop.live_runtime import preload_live_plugins
app = QApplication([])
# Fresh subprocess: the real SDK plugin has not already been imported by pytest.
preload_live_plugins()
from livekit.agents import Plugin
assert any(p.package == 'livekit.plugins.google' for p in Plugin.registered_plugins)
# The import itself is slow on a loaded machine: only what follows is timed.
print('IMPORTS_DONE', flush=True)
class Worker(QThread):
    ok = False
    def run(self):
        async def check():
            assert threading.current_thread() is not threading.main_thread()
            from livekit.plugins import google
            # Dummy key is only used to construct a model. No session is started.
            model = google.realtime.RealtimeModel(api_key='offline-placeholder')
            await model.aclose()
            self.ok = True
        asyncio.run(check())
worker = Worker()
worker.finished.connect(app.quit)
QTimer.singleShot(0, worker.start)
app.exec()
worker.wait()
assert worker.ok
print('REAL_GOOGLE_PLUGIN_WORKER_OK')
'''
    result = run_after_ready([sys.executable, '-c', code],
        env={**os.environ, 'PYTHONPATH': str(source), 'QT_QPA_PLATFORM': 'offscreen'},
        marker='IMPORTS_DONE', timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'REAL_GOOGLE_PLUGIN_WORKER_OK' in result.stdout
    assert 'Plugins must be registered on the main thread' not in result.stderr

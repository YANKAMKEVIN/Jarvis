"""One-shot camera still, captured in a short-lived helper process.

The camera is opened only for the single frame the user asked about, then
released: no stream, no recording, no file kept. Capture runs in a subprocess
(`python -m jarvis.tools.camera <out.jpg>`) so a stuck driver, a permission
prompt or a Qt multimedia crash can never block the voice session, and a hard
timeout always releases the camera. QtMultimedia ships with PySide6, so this
adds no dependency.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

CAPTURE_TIMEOUT_SECONDS = 15.0
# Auto-exposure needs a moment after the camera starts; the first frames are dark.
WARMUP_MS = 900


class CameraError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.message = message
        self.code = code


# Helper exit codes -> (French message, error code).
_HELPER_ERRORS = {
    3: ("Aucune caméra n'est disponible sur ce Mac.", "camera_unavailable"),
    4: ("L'accès à la caméra est refusé. Autorisez-le dans Réglages Système > "
        "Confidentialité et sécurité > Caméra.", "camera_permission_denied"),
    5: ("La caméra n'a pas pu prendre de photo.", "camera_capture_failed"),
}


class CameraCapture:
    def __init__(self, runner: Callable[..., subprocess.CompletedProcess] | None = None,
                 timeout: float = CAPTURE_TIMEOUT_SECONDS):
        self._run = runner if runner is not None else subprocess.run
        self.timeout = timeout

    def capture(self) -> Path:
        """Take one still and return its path (a private temp file the caller deletes)."""
        fd, name = tempfile.mkstemp(prefix="jarvis-camera-", suffix=".jpg")
        os.close(fd)
        path = Path(name)
        try:
            result = self._run(
                [sys.executable, "-m", "jarvis.tools.camera", str(path)],
                capture_output=True, text=True, timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            path.unlink(missing_ok=True)
            raise CameraError("La caméra n'a pas répondu à temps.", "camera_timeout")
        except OSError as error:
            path.unlink(missing_ok=True)
            raise CameraError(f"Capture impossible : {error}", "camera_capture_failed")
        if result.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            path.unlink(missing_ok=True)
            message, code = _HELPER_ERRORS.get(result.returncode, _HELPER_ERRORS[5])
            raise CameraError(message, code)
        return path


def _helper(out_path: str) -> int:
    """Runs in the helper process: open the default camera, save one JPEG, exit."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QTimer, Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtMultimedia import (QCamera, QImageCapture, QMediaCaptureSession,
                                      QMediaDevices)

    app = QGuiApplication([])
    device = QMediaDevices.defaultVideoInput()
    if device.isNull():
        return 3
    if hasattr(app, "checkPermission"):
        from PySide6.QtCore import QCameraPermission
        status = app.checkPermission(QCameraPermission())
        if status == Qt.PermissionStatus.Denied:
            return 4
        if status == Qt.PermissionStatus.Undetermined:
            granted = []
            # PySide6 needs a context QObject: (permission, context, functor).
            app.requestPermission(QCameraPermission(), app, lambda p: (granted.append(
                p.status() == Qt.PermissionStatus.Granted), QCoreApplication.quit()))
            app.exec()
            if not granted or not granted[0]:
                return 4

    outcome = {"code": 5}
    camera = QCamera(device)
    session = QMediaCaptureSession()
    session.setCamera(camera)
    still = QImageCapture()
    session.setImageCapture(still)

    def saved(_id, _path):
        outcome["code"] = 0
        app.quit()

    def failed(*_args):
        app.quit()

    still.imageSaved.connect(saved)
    still.errorOccurred.connect(failed)
    camera.errorOccurred.connect(failed)
    camera.start()
    QTimer.singleShot(WARMUP_MS, lambda: still.captureToFile(out_path))
    QTimer.singleShot(int(CAPTURE_TIMEOUT_SECONDS * 1000) - 2000, app.quit)
    app.exec()
    camera.stop()
    return outcome["code"]


if __name__ == "__main__":
    sys.exit(_helper(sys.argv[1]))

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
import threading
import time
from pathlib import Path
from typing import Callable

# The very first capture waits for the user to answer the macOS camera prompt.
PERMISSION_TIMEOUT_SECONDS = 30.0
# Prompt + camera warm-up + one frame; later captures finish in about a second.
CAPTURE_TIMEOUT_SECONDS = PERMISSION_TIMEOUT_SECONDS + 15.0
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


# AVAuthorizationStatus
_AV_NOT_DETERMINED, _AV_RESTRICTED, _AV_DENIED, _AV_AUTHORIZED = 0, 1, 2, 3


def native_camera_access(timeout: float = PERMISSION_TIMEOUT_SECONDS, avf=None,
                         pump: Callable[[float], None] | None = None) -> bool | None:
    """Ask macOS for camera access directly through AVFoundation.

    Qt refuses to request the permission when the *interpreter* has no
    NSCameraUsageDescription, which is always the case for the Python that the
    Jarvis.app launcher execs. AVFoundation has no such client-side check: TCC
    attributes the request to the responsible app (Jarvis.app, which declares
    the camera) and shows the system prompt. Returns True/False, or None when
    pyobjc's AVFoundation is unavailable (callers then fall back to Qt).
    """
    if avf is None:
        try:
            import AVFoundation as avf  # noqa: N813
        except ImportError:
            return None
    media = avf.AVMediaTypeVideo
    device = avf.AVCaptureDevice
    status = device.authorizationStatusForMediaType_(media)
    if status == _AV_AUTHORIZED:
        return True
    if status in (_AV_RESTRICTED, _AV_DENIED):
        return False

    done = threading.Event()
    answer = {}

    def handler(granted):
        answer["granted"] = bool(granted)
        done.set()

    device.requestAccessForMediaType_completionHandler_(media, handler)
    if pump is None:
        pump = _run_loop_for
    deadline = time.monotonic() + timeout
    while not done.is_set() and time.monotonic() < deadline:
        pump(0.1)
    return answer.get("granted", False)


def _run_loop_for(seconds: float) -> None:
    # The completion handler may be delivered through the main run loop.
    try:
        from Foundation import NSDate, NSRunLoop
        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(seconds))
    except ImportError:
        time.sleep(seconds)


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
    native = native_camera_access()
    if native is False:
        return 4
    if native is None and hasattr(app, "checkPermission"):
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
    # Permission is settled by now: the camera itself only needs a few seconds.
    QTimer.singleShot(10_000, app.quit)
    app.exec()
    camera.stop()
    return outcome["code"]


if __name__ == "__main__":
    sys.exit(_helper(sys.argv[1]))

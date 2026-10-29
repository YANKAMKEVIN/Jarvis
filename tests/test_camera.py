import subprocess
from pathlib import Path

import pytest

from jarvis.capabilities.camera import CameraCapability
from jarvis.tools.camera import CameraCapture, CameraError
from jarvis.tools.vision import VisionError


def runner(code=0, write=b"\xff\xd8jpeg"):
    calls = []

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        if write is not None and code == 0:
            Path(cmd[-1]).write_bytes(write)
        return subprocess.CompletedProcess(cmd, code, "", "")
    return run, calls


def test_capture_runs_the_helper_with_a_timeout():
    run, calls = runner()
    path = CameraCapture(runner=run, timeout=7).capture()
    try:
        assert path.read_bytes().startswith(b"\xff\xd8")
        cmd, kwargs = calls[0]
        assert cmd[1:3] == ["-m", "jarvis.tools.camera"] and kwargs["timeout"] == 7
    finally:
        path.unlink()


@pytest.mark.parametrize("code,error", [(3, "camera_unavailable"), (4, "camera_permission_denied"),
                                        (5, "camera_capture_failed"), (1, "camera_capture_failed")])
def test_helper_failures_map_to_clear_errors_and_leave_no_file(code, error):
    run, calls = runner(code=code)
    with pytest.raises(CameraError) as caught:
        CameraCapture(runner=run).capture()
    assert caught.value.code == error
    assert not Path(calls[0][0][-1]).exists()


def test_empty_capture_and_timeout_are_failures():
    run, calls = runner(write=b"")
    with pytest.raises(CameraError):
        CameraCapture(runner=run).capture()
    assert not Path(calls[0][0][-1]).exists()

    def slow(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])
    with pytest.raises(CameraError) as caught:
        CameraCapture(runner=slow).capture()
    assert caught.value.code == "camera_timeout"


class FakeCamera:
    def __init__(self, tmp_path, error=None):
        self.path = tmp_path / "still.jpg"
        self.error = error

    def capture(self):
        if self.error:
            raise self.error
        self.path.write_bytes(b"jpeg")
        return self.path


class FakeVision:
    def __init__(self, error=None):
        self.error = error
        self.prompts = []

    def analyze(self, path, prompt):
        assert Path(path).exists()
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return {"analysis": "Une tasse bleue sur un bureau.", "model": "m", "duration_ms": 12}


def test_describe_deletes_the_still_and_never_identifies(tmp_path):
    camera, vision = FakeCamera(tmp_path), FakeVision()
    r = CameraCapability(camera, vision).describe()
    assert r.ok and r.message == "Une tasse bleue sur un bureau." and r.data["image_kept"] is False
    assert not camera.path.exists()
    assert "n'identifie jamais" in vision.prompts[0]


def test_question_is_forwarded_and_failures_still_delete(tmp_path):
    camera, vision = FakeCamera(tmp_path), FakeVision(VisionError("Cle absente", code="vision_api_key_missing"))
    r = CameraCapability(camera, vision).describe("Que dit l'etiquette ?")
    assert not r.ok and r.error_code == "vision_api_key_missing"
    assert "Que dit l'etiquette ?" in vision.prompts[0]
    assert not camera.path.exists()


def test_camera_errors_skip_the_analysis(tmp_path):
    vision = FakeVision()
    camera = FakeCamera(tmp_path, CameraError("Accès refusé.", "camera_permission_denied"))
    r = CameraCapability(camera, vision).describe()
    assert not r.ok and r.error_code == "camera_permission_denied" and vision.prompts == []


class FakeAVF:
    """Stand-in for pyobjc's AVFoundation module."""

    AVMediaTypeVideo = "vide"

    def __init__(self, status, grant=None):
        self.requests = []
        outer = self

        class Device:
            @staticmethod
            def authorizationStatusForMediaType_(media):
                return status

            @staticmethod
            def requestAccessForMediaType_completionHandler_(media, handler):
                outer.requests.append(media)
                if grant is not None:
                    handler(grant)

        self.AVCaptureDevice = Device


@pytest.mark.parametrize("status, expected", [(3, True), (2, False), (1, False)])
def test_native_access_uses_the_existing_decision_without_prompting(status, expected):
    from jarvis.tools.camera import native_camera_access

    avf = FakeAVF(status)
    assert native_camera_access(avf=avf, pump=lambda s: None) is expected
    assert avf.requests == []


@pytest.mark.parametrize("grant", [True, False])
def test_native_access_prompts_once_when_undetermined(grant):
    from jarvis.tools.camera import native_camera_access

    avf = FakeAVF(0, grant=grant)
    assert native_camera_access(avf=avf, pump=lambda s: None) is grant
    assert avf.requests == ["vide"]


def test_unanswered_prompt_times_out_as_refused():
    from jarvis.tools.camera import native_camera_access

    pumped = []
    avf = FakeAVF(0, grant=None)  # the user never answers
    assert native_camera_access(timeout=0.05, avf=avf, pump=pumped.append) is False
    assert pumped  # the run loop was serviced while waiting


def test_capture_timeout_leaves_room_for_the_first_permission_prompt():
    from jarvis.tools.camera import CAPTURE_TIMEOUT_SECONDS, PERMISSION_TIMEOUT_SECONDS

    assert CAPTURE_TIMEOUT_SECONDS > PERMISSION_TIMEOUT_SECONDS

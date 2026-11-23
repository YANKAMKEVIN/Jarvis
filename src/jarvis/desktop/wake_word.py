"""Local wake word: microphone PCM reaches Gemini only after « Jarvis ».

Detection runs entirely on this Mac (openWakeWord, ONNX). Nothing here opens a
network connection except the one-time model download in `load_engine`, which
fetches model files, never audio. PortAudio callbacks only enqueue; scoring
happens on a dedicated thread so capture never blocks.
"""
from __future__ import annotations

import hashlib
import os
from array import array
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import monotonic

WAKE_SAMPLE_RATE = 16000
WAKE_MODEL = "hey_jarvis"
DEFAULT_THRESHOLD = 0.5
DEFAULT_IDLE_SECONDS = 45
REFRACTORY_SECONDS = 2.0
QUEUE_BLOCKS = 50  # One second of 20 ms capture blocks.
# SHA-256 of the ONNX files openWakeWord 0.6 downloads from its v0.5.1 GitHub
# release (computed 2026-11-23). A file that differs is refused: the detector
# decides when the microphone reaches Gemini. The models are CC BY-NC-SA 4.0,
# so they are verified, not shipped in this repository.
MODEL_SHA256 = {
    "hey_jarvis_v0.1.onnx": "94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb",
    "melspectrogram.onnx": "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    "embedding_model.onnx": "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
}


class WakeWordUnavailable(Exception):
    """User-facing: the local detector cannot run, so the gate stays closed."""


def _env_number(name, default, low, high, kind=float):
    try:
        value = kind(os.environ.get(name, default))
    except ValueError:
        return default
    return min(max(value, low), high)


def wake_threshold():
    """Score that counts as « Jarvis »; JARVIS_WAKE_THRESHOLD tunes false wakes."""
    return _env_number("JARVIS_WAKE_THRESHOLD", DEFAULT_THRESHOLD, 0.2, 0.95)


def wake_idle_seconds():
    """Silence after which Jarvis goes back to local standby."""
    return _env_number("JARVIS_WAKE_IDLE_SECONDS", DEFAULT_IDLE_SECONDS, 15, 300, int)


class Downsampler:
    """24 kHz → 16 kHz mono PCM16 (3 samples in, 2 out), stateful across blocks.

    A two-tap average before each pick is a crude low-pass; enough for a
    keyword model trained on 16 kHz speech, and cheap on a 20 ms block.
    """

    def __init__(self):
        self.pending = array("h")

    def feed(self, pcm):
        samples = self.pending
        samples.frombytes(pcm[: len(pcm) - len(pcm) % 2])
        usable = len(samples) - len(samples) % 3
        out = array("h")
        for index in range(0, usable, 3):
            a, b, c = samples[index], samples[index + 1], samples[index + 2]
            out.append((a + b) // 2)
            out.append((b + c) // 2)
        self.pending = samples[usable:]
        return out.tobytes()

    def reset(self):
        self.pending = array("h")


class OpenWakeWordEngine:
    """openWakeWord's pre-trained `hey_jarvis` model on onnxruntime."""

    frame_samples = 1280  # 80 ms at 16 kHz, the model's native step.

    def __init__(self, model, numpy):
        self.model = model
        self.numpy = numpy

    def score(self, pcm16k):
        scores = self.model.predict(self.numpy.frombuffer(pcm16k, dtype=self.numpy.int16))
        return max(scores.values(), default=0.0)

    def reset(self):
        self.model.reset()


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_models(directory, expected=None):
    """Names of missing model files; raises if a present one was modified."""
    missing = []
    for name, sha256 in (MODEL_SHA256 if expected is None else expected).items():
        path = Path(directory) / name
        if not path.is_file():
            missing.append(name)
        elif file_sha256(path) != sha256:
            raise WakeWordUnavailable(f"Le modèle local « {name} » ne correspond pas à la version vérifiée. "
                                      "Supprimez-le puis relancez Jarvis avec Internet pour le retélécharger.")
    return missing


def models_directory():
    import openwakeword
    return Path(openwakeword.__file__).resolve().parent / "resources" / "models"


def load_engine(download=True, directory=None):
    try:
        import numpy
        import openwakeword  # noqa: F401 - availability check
        from openwakeword.model import Model
    except (ImportError, OSError):
        raise WakeWordUnavailable("Mot d’éveil indisponible. Installez-le : "
                                  "python -m pip install -e '.[desktop,live,wake]'.") from None

    def build():
        return Model(wakeword_models=[WAKE_MODEL], inference_framework="onnx")

    directory = directory or models_directory()
    # Checked before anything is loaded: a modified file never runs.
    if not check_models(directory):
        try:
            return OpenWakeWordEngine(build(), numpy)
        except Exception:
            pass
    if not download:
        raise WakeWordUnavailable("Modèle « hey_jarvis » introuvable. Lancez Jarvis une fois "
                                  "avec Internet pour le télécharger.")
    try:
        # Model files only (a few MB from the openWakeWord GitHub release).
        from openwakeword.utils import download_models
        download_models(model_names=[WAKE_MODEL], target_directory=str(directory))
    except Exception:
        raise WakeWordUnavailable("Le modèle local du mot d’éveil n’a pas pu être chargé. "
                                  "Vérifiez Internet pour le premier téléchargement, puis réessayez.") from None
    if check_models(directory):
        raise WakeWordUnavailable("Téléchargement du modèle du mot d’éveil incomplet. Réessayez avec Internet.")
    try:
        return OpenWakeWordEngine(build(), numpy)
    except Exception:
        raise WakeWordUnavailable("Le modèle local du mot d’éveil n’a pas pu être chargé. "
                                  "Vérifiez Internet pour le premier téléchargement, puis réessayez.") from None


class WakeWordDetector:
    """Synchronous core: 24 kHz capture blocks in, True once per « Jarvis »."""

    def __init__(self, engine, threshold=None, clock=monotonic, refractory=REFRACTORY_SECONDS):
        self.engine = engine
        self.threshold = wake_threshold() if threshold is None else threshold
        self.clock = clock
        self.refractory = refractory
        self.resampler = Downsampler()
        self.buffer = bytearray()
        self.quiet_until = 0.0

    def process(self, pcm24k):
        self.buffer.extend(self.resampler.feed(pcm24k))
        frame_bytes = self.engine.frame_samples * 2
        detected = False
        while len(self.buffer) >= frame_bytes:
            frame = bytes(self.buffer[:frame_bytes])
            del self.buffer[:frame_bytes]
            score = self.engine.score(frame)
            if not detected and score >= self.threshold and self.clock() >= self.quiet_until:
                detected = True
        if detected:
            # One utterance, one wake: forget the features that just fired.
            self.quiet_until = self.clock() + self.refractory
            self.reset()
        return detected

    def reset(self):
        self.buffer.clear()
        self.resampler.reset()
        self.engine.reset()


class WakeListener:
    """Runs a detector off the PortAudio thread with a bounded queue.

    `on_wake(blocks)` receives the capture blocks queued after the detection,
    so speech that follows « Jarvis » without a pause is not lost.
    """

    def __init__(self, detector, on_wake=None):
        self.detector = detector
        self.on_wake = on_wake
        self.blocks = Queue(maxsize=QUEUE_BLOCKS)
        self.lock = Lock()
        self.stopped = Event()
        self.thread = None
        self.failed = False

    def feed(self, block):
        try:
            self.blocks.put_nowait(bytes(block))
        except Full:
            try:
                self.blocks.get_nowait()  # Drop the oldest, never block capture.
            except Empty:
                pass
            try:
                self.blocks.put_nowait(bytes(block))
            except Full:
                pass

    def _drain(self):
        drained = []
        while True:
            try:
                drained.append(self.blocks.get_nowait())
            except Empty:
                return drained

    def pump(self, timeout=0.0):
        """Score queued audio; returns True when the wake word fired."""
        try:
            block = self.blocks.get(timeout=timeout) if timeout else self.blocks.get_nowait()
        except Empty:
            return False
        with self.lock:
            fired = self.detector.process(block)
            if not fired:
                return False
            remaining = self._drain()
        if self.on_wake is not None:
            self.on_wake(remaining)
        return True

    def reset(self):
        with self.lock:
            self._drain()
            self.detector.reset()

    def _run(self):
        while not self.stopped.is_set():
            try:
                self.pump(timeout=0.1)
            except Exception:
                self.failed = True  # The gate stays closed; the runtime reports it.
                return

    def start(self):
        if self.thread is None:
            self.thread = Thread(target=self._run, name="jarvis-wake-word", daemon=True)
            self.thread.start()

    def close(self):
        self.stopped.set()
        if self.thread is not None:
            self.thread.join(timeout=1)
            self.thread = None
        self._drain()


def create_wake_listener():
    return WakeListener(WakeWordDetector(load_engine()))

"""openWakeWord models are verified by SHA-256 before use (idea 34)."""
import hashlib
import sys
import types

import pytest

from jarvis.desktop import wake_word
from jarvis.desktop.wake_word import WakeWordUnavailable, check_models, load_engine


def expected_for(directory, files):
    table = {}
    for name, data in files.items():
        (directory / name).write_bytes(data)
        table[name] = hashlib.sha256(data).hexdigest()
    return table


def test_known_hashes_are_pinned_for_the_three_onnx_files():
    assert set(wake_word.MODEL_SHA256) == {"hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"}
    assert all(len(value) == 64 for value in wake_word.MODEL_SHA256.values())


def test_missing_files_are_listed_and_modified_ones_refused(tmp_path):
    table = expected_for(tmp_path, {"a.onnx": b"good"})
    table["b.onnx"] = "0" * 64
    assert check_models(tmp_path, table) == ["b.onnx"]
    (tmp_path / "a.onnx").write_bytes(b"tampered")
    with pytest.raises(WakeWordUnavailable, match="ne correspond pas"):
        check_models(tmp_path, table)


@pytest.fixture
def fake_openwakeword(monkeypatch, tmp_path):
    state = {"downloads": 0, "built": 0, "payload": {}}
    package = types.ModuleType("openwakeword")
    model_module = types.ModuleType("openwakeword.model")
    utils = types.ModuleType("openwakeword.utils")

    class Model:
        def __init__(self, **kwargs):
            state["built"] += 1

    def download_models(model_names, target_directory):
        state["downloads"] += 1
        for name, data in state["payload"].items():
            (tmp_path / name).write_bytes(data)

    model_module.Model = Model
    utils.download_models = download_models
    monkeypatch.setitem(sys.modules, "openwakeword", package)
    monkeypatch.setitem(sys.modules, "openwakeword.model", model_module)
    monkeypatch.setitem(sys.modules, "openwakeword.utils", utils)
    monkeypatch.setitem(sys.modules, "numpy", types.ModuleType("numpy"))
    return state


def test_download_is_verified_before_the_model_is_built(fake_openwakeword, tmp_path, monkeypatch):
    good = {name: name.encode() for name in wake_word.MODEL_SHA256}
    monkeypatch.setattr(wake_word, "MODEL_SHA256", {n: hashlib.sha256(d).hexdigest() for n, d in good.items()})
    fake_openwakeword["payload"] = {**good, "hey_jarvis_v0.1.onnx": b"evil"}
    with pytest.raises(WakeWordUnavailable):
        load_engine(directory=tmp_path)
    assert fake_openwakeword["built"] == 0
    for path in tmp_path.iterdir():
        path.unlink()
    fake_openwakeword["payload"] = good
    engine = load_engine(directory=tmp_path)
    assert fake_openwakeword["downloads"] == 2 and fake_openwakeword["built"] == 1
    assert engine is not None
    load_engine(directory=tmp_path)  # verified files present: no new download
    assert fake_openwakeword["downloads"] == 2


def test_offline_without_models_is_explicit(fake_openwakeword, tmp_path):
    with pytest.raises(WakeWordUnavailable, match="introuvable"):
        load_engine(download=False, directory=tmp_path)

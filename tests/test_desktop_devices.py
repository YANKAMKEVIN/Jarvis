import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import asyncio
from types import SimpleNamespace as NS
import pytest
from PySide6.QtWidgets import QApplication
from jarvis.desktop.devices import AudioDeviceError, catalog, resolve_device
from jarvis.desktop.audio_settings import AudioJob
from jarvis.desktop.live_audio import LocalAudio


class Devices:
    def __init__(self):
        self.rows = [{'name': 'USB mic', 'hostapi': 0, 'max_input_channels': 1, 'max_output_channels': 0},
                     {'name': 'Speaker', 'hostapi': 0, 'max_input_channels': 0, 'max_output_channels': 2}]
        self.streams = []
    def query_devices(self): return self.rows
    def query_hostapis(self): return [{'name': 'Core Audio'}]
    def check_input_settings(self, **kwargs): pass
    def check_output_settings(self, **kwargs): pass
    def stream(self, direction, **kwargs):
        owner = self
        class Stream:
            closed = active = False
            def start(self):
                self.active = True
                if direction == 'input': kwargs['callback'](b'\x00\x40' * 480, 480, None, None)
                else: kwargs['callback'](bytearray(960), 480, NS(outputBufferDacTime=0, currentTime=0), None)
            def stop(self): self.active = False
            def abort(self): self.active = False
            def close(self): self.closed = True
        stream = Stream()
        stream.direction, stream.device = direction, kwargs.get('device')
        owner.streams.append(stream)
        return stream
    def RawInputStream(self, **kwargs): return self.stream('input', **kwargs)
    def RawOutputStream(self, **kwargs): return self.stream('output', **kwargs)


CHOICE = {'name': 'USB mic', 'hostapi': 'Core Audio'}


def test_named_selection_survives_reordering_and_never_silently_falls_back():
    devices = Devices()
    assert resolve_device(devices, CHOICE, 'input') == 0
    devices.rows.reverse()
    assert resolve_device(devices, CHOICE, 'input') == 1
    devices.rows = devices.rows[:1]
    with pytest.raises(AudioDeviceError, match='déconnecté'):
        resolve_device(devices, CHOICE, 'input')
    devices.rows *= 2
    with pytest.raises(AudioDeviceError, match='même nom'):
        resolve_device(devices, {'name': 'Speaker', 'hostapi': 'Core Audio'}, 'output')
    assert resolve_device(devices, None, 'input') is None  # Only an explicit system-default choice.


def test_local_audio_uses_chosen_indices_and_muted_open_never_opens_input():
    async def scenario():
        devices = Devices()
        audio = LocalAudio(asyncio.get_running_loop(), devices)
        audio.configure_devices(CHOICE, {'name': 'Speaker', 'hostapi': 'Core Audio'})
        audio.open(microphone=False)
        assert len(devices.streams) == 1 and devices.streams[0].device == 1
        assert not audio.mic_open and audio.microphone is None
        audio.set_microphone(True)
        assert devices.streams[-1].device == 0 and audio.mic_open
        audio.close()
        assert all(s.closed for s in devices.streams)
    asyncio.run(scenario())


def test_probes_open_only_requested_direction_and_close_without_sdk_or_network():
    instance = QApplication.instance() or QApplication([])
    for kind, direction in (('microphone', 'input'), ('speaker', 'output')):
        devices = Devices()
        events = []
        job = AudioJob(kind, CHOICE, None, devices=devices, duration=0.05)
        job.event.connect(events.append)
        job.start()
        assert job.wait(2000)
        instance.processEvents()
        assert len(devices.streams) == 1 and devices.streams[0].direction == direction
        assert devices.streams[0].closed
        assert events[-1]['state'] == 'idle'
        assert all('data' not in e and 'pcm' not in e for e in events)
        if kind == 'microphone':
            assert any(e.get('level', 0) > 0 for e in events)


def test_probe_failure_releases_partial_stream_and_sanitizes_backend_error():
    instance = QApplication.instance() or QApplication([])
    devices = Devices()
    original = devices.RawInputStream
    def broken(**kwargs):
        stream = original(**kwargs)
        def fail(): raise RuntimeError('PRIVATE_DEVICE_PAYLOAD')
        stream.start = fail
        return stream
    devices.RawInputStream = broken
    events = []
    job = AudioJob('microphone', CHOICE, devices=devices)
    job.event.connect(events.append)
    job.start()
    assert job.wait(1000)
    instance.processEvents()
    assert devices.streams[0].closed and events[-1]['state'] == 'error'
    assert 'PRIVATE' not in str(events)


def test_stopped_device_is_reported_instead_of_claiming_microphone_is_live():
    async def scenario():
        devices = Devices()
        audio = LocalAudio(asyncio.get_running_loop(), devices)
        audio.open()
        audio.check_health()
        audio.microphone.active = False
        with pytest.raises(AudioDeviceError, match='arrêté'):
            audio.check_health()
        audio.microphone.active = True
        audio.set_microphone(False)
        audio.check_health()  # Explicit mute is not a device failure.
        audio.speaker.active = False
        with pytest.raises(AudioDeviceError, match='arrêté'):
            audio.check_health()
        audio.close()
    asyncio.run(scenario())


def test_probe_can_be_cancelled_before_five_seconds_and_closes_stream():
    instance = QApplication.instance() or QApplication([])
    devices = Devices()
    job = AudioJob('microphone', CHOICE, devices=devices, duration=5)
    started = []
    job.event.connect(lambda event: started.append(event))
    job.start()
    from PySide6.QtTest import QTest
    for _ in range(100):
        if devices.streams and devices.streams[0].active:
            break
        instance.processEvents()
        QTest.qWait(5)
    assert devices.streams and devices.streams[0].active
    # The job only needs an explicit stop; no timeout or forceful thread kill.
    job.stop()
    assert job.wait(1000)
    instance.processEvents()
    assert all(stream.closed for stream in devices.streams)
    assert started[-1]['state'] == 'idle'

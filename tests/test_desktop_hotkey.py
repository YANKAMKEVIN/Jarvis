import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import ctypes as C
from PySide6.QtWidgets import QApplication
from jarvis.desktop.hotkey import CarbonBackend, GlobalHotkey, HotkeyID, SIGNATURE


def app():
    return QApplication.instance() or QApplication([])


def test_global_registration_queues_only_our_callback_and_disable_drops_pending_events():
    instance = app()
    class Backend:
        def __init__(self): self.closed = 0
        def start(self, callback): self.callback = callback; return True
        def close(self): self.closed += 1
    backend = Backend()
    received = []
    manager = GlobalHotkey(lambda: received.append(True), backend_factory=lambda: backend, platform='darwin')
    manager.set_enabled(True)
    assert manager.active
    backend.callback()
    assert not received  # Carbon callback never directly calls UI.
    instance.processEvents()
    assert received == [True]
    backend.callback()
    manager.set_enabled(False)
    instance.processEvents()
    assert received == [True] and not manager.active and backend.closed


def test_conflict_platform_and_demo_never_claim_registration_or_load_backend():
    instance = app()
    class Conflict:
        closed = False
        def start(self, callback): return False
        def close(self): self.closed = True
    backend = Conflict()
    manager = GlobalHotkey(lambda: None, backend_factory=lambda: backend, platform='darwin')
    manager.set_enabled(True)
    assert not manager.active and backend.closed and 'indisponible' in manager.message
    for kwargs in ({'platform': 'linux'}, {'platform': 'darwin', 'demo': True}):
        untouched = GlobalHotkey(lambda: None, backend_factory=lambda: (_ for _ in ()).throw(AssertionError()), **kwargs)
        untouched.set_enabled(True)
        assert not untouched.active


def test_native_callback_filters_identifier_and_cleans_partial_registration():
    class API:
        fail = False
        removed = unregistered = 0
        def GetApplicationEventTarget(self): return 123
        def InstallEventHandler(self, target, callback, count, spec, data, out):
            out._obj.value = 456
            self.callback = callback
            return 0
        def RegisterEventHotKey(self, key, modifiers, identifier, target, options, out):
            assert key == 49 and modifiers == 768 and identifier.signature == SIGNATURE
            assert options == 1
            if self.fail: return -1
            out._obj.value = 789
            return 0
        def GetEventParameter(self, event, name, kind, actual, size, actual_size, out):
            identifier = C.cast(out, C.POINTER(HotkeyID)).contents
            identifier.signature, identifier.id = self.signature, 1
            return 0
        def UnregisterEventHotKey(self, value): self.unregistered += 1; return 0
        def RemoveEventHandler(self, value): self.removed += 1; return 0
    backend = CarbonBackend.__new__(CarbonBackend)
    backend.api = API()
    backend.handler, backend.hotkey, backend.callback = C.c_void_p(), C.c_void_p(), None
    received = []
    assert backend.start(lambda: received.append(True))
    backend.api.signature = 0
    assert backend.api.callback(None, None, None) != 0 and not received
    backend.api.signature = SIGNATURE
    assert backend.api.callback(None, None, None) == 0 and received == [True]
    assert backend.close() and backend.api.removed == 1 and backend.api.unregistered == 1
    backend.api.fail = True
    assert not backend.start(lambda: None)
    assert backend.api.removed == 2 and not backend.handler.value

"""One macOS Carbon hotkey, never an arbitrary keyboard monitor."""
import ctypes as C
import sys
from PySide6.QtCore import QObject, Signal, Qt


def fourcc(value):
    return int.from_bytes(value.encode('ascii'), 'big')


class EventType(C.Structure):
    _fields_ = [('eventClass', C.c_uint32), ('eventKind', C.c_uint32)]


class HotkeyID(C.Structure):
    _fields_ = [('signature', C.c_uint32), ('id', C.c_uint32)]


CALLBACK = C.CFUNCTYPE(C.c_int32, C.c_void_p, C.c_void_p, C.c_void_p)
SIGNATURE = fourcc('Jrvs')


class CarbonBackend:
    def __init__(self, modifiers=768, identifier=1):
        self.modifiers=modifiers
        self.identifier=identifier
        self.api = C.CDLL('/System/Library/Frameworks/Carbon.framework/Carbon')
        api = self.api
        api.GetApplicationEventTarget.argtypes = []
        api.GetApplicationEventTarget.restype = C.c_void_p
        api.InstallEventHandler.argtypes = [C.c_void_p, CALLBACK, C.c_uint32,
            C.POINTER(EventType), C.c_void_p, C.POINTER(C.c_void_p)]
        api.InstallEventHandler.restype = C.c_int32
        api.RegisterEventHotKey.argtypes = [C.c_uint32, C.c_uint32, HotkeyID,
            C.c_void_p, C.c_uint32, C.POINTER(C.c_void_p)]
        api.RegisterEventHotKey.restype = C.c_int32
        api.GetEventKind.argtypes=[C.c_void_p]
        api.GetEventKind.restype=C.c_uint32
        api.GetEventParameter.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32,
            C.c_void_p, C.c_uint32, C.c_void_p, C.c_void_p]
        api.GetEventParameter.restype = C.c_int32
        for name in ('UnregisterEventHotKey', 'RemoveEventHandler'):
            getattr(api, name).argtypes = [C.c_void_p]
            getattr(api, name).restype = C.c_int32
        self.handler = C.c_void_p()
        self.hotkey = C.c_void_p()
        self.callback = None

    def start(self, trigger, released=None):
        def receive(next_handler, event, userdata):
            try:
                identifier = HotkeyID()
                result = self.api.GetEventParameter(event, fourcc('----'), fourcc('hkid'),
                    None, C.sizeof(identifier), None, C.byref(identifier))
                if result == 0 and identifier.signature == SIGNATURE and identifier.id == getattr(self,'identifier',1):
                    callback = released if released is not None and self.api.GetEventKind(event)==9 else trigger
                    callback()  # Emits a queued Qt signal; never calls Qt UI here.
                    return 0
            except Exception:
                pass
            return -9874  # eventNotHandledErr
        self.callback = CALLBACK(receive)  # Keep the C callback alive until removal.
        target = self.api.GetApplicationEventTarget()
        kinds=(6,9) if released is not None else (6,)
        spec=(EventType*len(kinds))(*(EventType(fourcc('keyb'),kind) for kind in kinds))
        if self.api.InstallEventHandler(target, self.callback, len(kinds), spec, None, C.byref(self.handler)):
            self.close()
            return False
        if self.api.RegisterEventHotKey(49, getattr(self,'modifiers',768), HotkeyID(SIGNATURE,getattr(self,'identifier',1)),
                                       target, 1, C.byref(self.hotkey)):  # kEventHotKeyExclusive
            self.close()
            return False
        return True

    def close(self):
        # Keep callback storage alive even if OS cleanup reports a failure.
        if self.hotkey.value:
            if self.api.UnregisterEventHotKey(self.hotkey) == 0:
                self.hotkey = C.c_void_p()
        if self.handler.value:
            if self.api.RemoveEventHandler(self.handler) == 0:
                self.handler = C.c_void_p()
        if not self.handler.value:
            self.callback = None
        return not self.handler.value and not self.hotkey.value


class GlobalHotkey(QObject):
    activated = Signal()
    changed = Signal()

    def __init__(self, callback, parent=None, backend_factory=CarbonBackend, platform=None, demo=False):
        super().__init__(parent)
        self.platform = platform or sys.platform
        self.demo = demo
        self.factory = backend_factory
        self.backend = None
        self.active = False
        self.on_trigger = callback
        self.message = 'Raccourci local uniquement.'
        self.activated.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)

    def _dispatch(self):
        if self.active:
            self.on_trigger()

    def set_enabled(self, enabled):
        if not self.close():
            self.message = 'Le précédent raccourci n’a pas pu être libéré. Quittez puis relancez Jarvis.'
            self.changed.emit()
            return
        if not enabled:
            self.message = 'Raccourci global désactivé · raccourci local disponible.'
        elif self.demo:
            self.message = 'Démo · raccourci local uniquement.'
        elif self.platform != 'darwin':
            self.message = 'Raccourci global disponible sur macOS uniquement.'
        else:
            try:
                self.backend = self.factory()
                self.active = bool(self.backend.start(self.activated.emit))
            except Exception:
                self.active = False
            if self.active:
                self.message = '⌘⇧Espace actif depuis les autres applications.'
            else:
                self.close()
                self.message = '⌘⇧Espace indisponible. Vérifiez les raccourcis macOS ou d’autres applications, puis réessayez.'
        self.changed.emit()

    def close(self):
        self.active = False
        if self.backend is not None:
            try:
                if self.backend.close() is False:
                    return False
            except Exception:
                return False
            # Keep the backend alive so its callback cannot be collected during cleanup.
        return True


class HoldHotkey(QObject):
    transition=Signal(int,bool)
    changed=Signal()
    def __init__(self,begin,end,parent=None,backend_factory=None,platform=None,demo=False):
        super().__init__(parent)
        self.factory=backend_factory or (lambda:CarbonBackend(modifiers=(1<<8)|(1<<11),identifier=2))
        self.platform=platform or sys.platform;self.demo=demo
        self.backend=None;self.active=False;self.begin=begin;self.end=end;self.generation=0
        self.message='Maintien pour parler désactivé.'
        self.transition.connect(self.dispatch,Qt.ConnectionType.QueuedConnection)
    def dispatch(self,generation,pressed):
        if generation==self.generation and self.active:
            self.begin() if pressed else self.end()
    def set_enabled(self,enabled):
        if not self.close():
            self.message='Raccourci de maintien non libéré. Relancez Jarvis.'
        elif not enabled:self.message='Maintien pour parler désactivé.'
        elif self.demo or self.platform!='darwin':self.message='Espace sur le compagnon · raccourci global indisponible.'
        else:
            try:
                self.backend=self.factory()
                generation=self.generation
                self.active=bool(self.backend.start(lambda:self.transition.emit(generation,True),lambda:self.transition.emit(generation,False)))
            except Exception:self.active=False
            self.message='Maintenir ⌘⌥Espace pour parler.' if self.active else '⌘⌥Espace indisponible · Espace sur le compagnon reste disponible.'
            if not self.active:self.close()
        self.changed.emit()
    def close(self):
        self.generation+=1;self.active=False;self.end()
        if self.backend is not None:
            try:return self.backend.close() is not False
            except Exception:return False
        return True

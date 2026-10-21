"""Qt bridge; asyncio and all Live SDK objects stay on this worker thread."""
import asyncio
from PySide6.QtCore import QThread, Signal
from jarvis.desktop.live_runtime import LiveRuntime


class LiveWorker(QThread):
    event = Signal(object)

    def __init__(self, parent=None, runtime_factory=LiveRuntime):
        super().__init__(parent)
        self.runtime = runtime_factory(self.event.emit)

    def run(self):
        try:
            asyncio.run(self.runtime.run())
        except Exception:
            self.event.emit({"type": "state", "state": "error", "mic_open": False,
                "message": "La session vocale n’a pas pu se fermer correctement. Vérifiez les actions en cours avant de réessayer."})

    def stop(self):
        self.runtime.stop()

    def set_muted(self, muted):
        self.runtime.set_muted(muted)

    def set_push_to_talk(self,enabled):
        self.runtime.set_push_to_talk(enabled)

    def finish_push_to_talk(self):
        self.runtime.finish_push_to_talk()

    def interrupt(self):
        self.runtime.interrupt()

    def run_routine(self,name):
        self.runtime.run_routine(name)

    def announce(self, message):
        self.runtime.announce(message)

    def set_sounds(self, enabled):
        self.runtime.set_sounds(enabled)

    def cancel_task(self, task_id=None):
        self.runtime.cancel_task(task_id)

    def set_devices(self, input_choice, output_choice):
        self.runtime.set_devices(input_choice, output_choice)


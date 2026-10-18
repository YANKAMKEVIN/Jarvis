"""Explicit local-only device scan and short audio tests, off the Qt thread."""
import math
import time
from threading import Event
from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QGridLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget
from jarvis.desktop.devices import AudioDeviceError, RATE, catalog, pcm_level, resolve_device, test_tone


class AudioJob(QThread):
    event = Signal(object)

    def __init__(self, kind, input_choice=None, output_choice=None, parent=None, devices=None, duration=5.0):
        super().__init__(parent)
        self.kind = kind
        self.input_choice, self.output_choice = input_choice, output_choice
        self.devices, self.duration = devices, duration
        self.stop_requested = Event()

    def stop(self):
        self.stop_requested.set()

    def run(self):
        stream = None
        failure = None
        try:
            if self.stop_requested.is_set():
                return
            devices = self.devices
            if devices is None:
                import sounddevice as devices
            if self.kind == 'scan':
                self.event.emit({'type': 'catalog', 'devices': catalog(devices)})
                return
            direction = 'input' if self.kind == 'microphone' else 'output'
            choice = self.input_choice if direction == 'input' else self.output_choice
            index = resolve_device(devices, choice, direction)
            if self.stop_requested.is_set():
                return
            level = [0.0]
            tone = test_tone() if direction == 'output' else b''
            position = [0]
            def input_callback(data, frames, timing, status):
                level[0] = pcm_level(data)  # Nothing is recorded or forwarded.
            def output_callback(data, frames, timing, status):
                block = tone[position[0]:position[0] + len(data)]
                position[0] += len(block)
                data[:] = block + bytes(len(data) - len(block))
            constructor = devices.RawInputStream if direction == 'input' else devices.RawOutputStream
            stream = constructor(device=index, samplerate=RATE, channels=1, dtype='int16',
                blocksize=480, callback=input_callback if direction == 'input' else output_callback)
            stream.start()
            self.event.emit({'type': 'audio_test', 'state': self.kind,
                             'message': 'Test micro local · rien n’est envoyé à Gemini.' if direction == 'input' else
                                        'Signal sonore local · vérifiez la sortie choisie.'})
            duration = self.duration if direction == 'input' else len(tone) / (RATE * 2) + 0.5
            deadline = time.monotonic() + duration
            while not self.stop_requested.is_set() and time.monotonic() < deadline:
                if direction == 'input':
                    self.event.emit({'type': 'test_level', 'level': level[0]})
                self.stop_requested.wait(0.05)
        except AudioDeviceError as error:
            failure = str(error)
        except Exception:
            failure = 'Test audio impossible. Vérifiez les périphériques et les autorisations Microphone de macOS.'
        finally:
            if stream is not None:
                try:
                    stream.abort()
                except Exception:
                    pass
                try:
                    stream.close()
                except Exception:
                    failure = 'La fermeture du périphérique de test a échoué. Vérifiez-le avant de démarrer Jarvis.'
            self.event.emit({'type': 'test_level', 'level': 0.0})
            self.event.emit({'type': 'audio_test', 'state': 'error' if failure else 'idle',
                             'message': failure or ('Test terminé · périphérique fermé.' if self.kind != 'scan' else 'Liste des périphériques actualisée.')})


class AudioSettings(QWidget):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.updating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.input = QComboBox()
        self.output = QComboBox()
        for combo in (self.input, self.output):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(12)
        self.input.setAccessibleName('Microphone de Jarvis')
        self.output.setAccessibleName('Sortie audio de Jarvis')
        for combo, choice in ((self.input, controller.input_choice), (self.output, controller.output_choice)):
            combo.addItem('Périphérique système par défaut', None)
            if choice:
                combo.addItem(choice['name'] + ' · choix enregistré', choice)
                combo.setCurrentIndex(1)
        form = QFormLayout()
        form.addRow('Microphone', self.input)
        form.addRow('Sortie', self.output)
        layout.addLayout(form)
        if controller.device_config_invalid:
            self.input.addItem('Choix enregistré invalide · sélectionner à nouveau', None)
            self.input.setCurrentIndex(self.input.count() - 1)
        self.input.currentIndexChanged.connect(self.selection_changed)
        self.output.currentIndexChanged.connect(self.selection_changed)
        self.reset = QPushButton('Utiliser les périphériques système')
        self.reset.clicked.connect(self.reset_selection)
        layout.addWidget(self.reset)
        controls = QGridLayout()
        self.refresh = QPushButton('Actualiser')
        self.test_mic = QPushButton('Tester le micro')
        self.test_speaker = QPushButton('Tester la sortie')
        self.stop = QPushButton('Arrêter le test')
        for index, widget in enumerate((self.refresh, self.stop, self.test_mic, self.test_speaker)):
            controls.addWidget(widget, index // 2, index % 2)
        layout.addLayout(controls)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setValue(0)
        self.level.setTextVisible(False)
        self.level.setAccessibleName('Niveau du micro pendant le test local')
        layout.addWidget(self.level)
        self.notice = QLabel('Actualisez la liste pour choisir un périphérique. Les tests sont locaux et ferment le micro après 5 secondes.')
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.refresh.clicked.connect(lambda: controller.start_audio_job('scan'))
        self.test_mic.clicked.connect(lambda: controller.start_audio_job('microphone'))
        self.test_speaker.clicked.connect(lambda: controller.start_audio_job('speaker'))
        self.stop.clicked.connect(controller.stop_audio_job)
        controller.audio_event.connect(self.handle_event)
        controller.audio_levels.connect(self.live_level)
        controller.changed.connect(self.render)
        self.render()

    def selection_changed(self):
        if not self.updating:
            self.controller.set_devices(self.input.currentData(), self.output.currentData())
            self.notice.setText('Choix mémorisé pour le prochain démarrage du vocal.')

    def live_level(self, incoming, outgoing):
        if self.controller.audio_worker is None:
            self.handle_event({'type': 'test_level', 'level': incoming})

    def reset_selection(self):
        self.updating = True
        try:
            self.input.setCurrentIndex(0)
            self.output.setCurrentIndex(0)
        finally:
            self.updating = False
        self.controller.set_devices(None, None)
        self.notice.setText('Périphériques système choisis pour le prochain démarrage.')

    def handle_event(self, event):
        if event['type'] == 'catalog':
            self.updating = True
            try:
                for combo, choice, direction in ((self.input, self.controller.input_choice, 'input'),
                                                  (self.output, self.controller.output_choice, 'output')):
                    combo.clear()
                    combo.addItem('Périphérique système par défaut', None)
                    choices = []
                    for device in event['devices']:
                        value = device['choice']
                        if device[direction] and value not in choices:
                            choices.append(value)
                            combo.addItem(value['name'] + ' · ' + value['hostapi'], value)
                    if choice and choice not in choices:
                        combo.addItem(choice['name'] + ' · déconnecté', choice)
                    combo.setCurrentIndex(next((i for i in range(combo.count()) if combo.itemData(i) == choice), 0))
            finally:
                self.updating = False
        elif event['type'] == 'test_level':
            self.level.setValue(round(min(1.0, math.sqrt(max(0.0, event['level'])) * 2.2) * 100))
        elif event['type'] == 'audio_test':
            self.notice.setText(event['message'])

    def render(self):
        c = self.controller
        idle = not c.demo and c.voice_worker is None and c.audio_worker is None
        for widget in (self.input, self.output, self.reset, self.refresh, self.test_mic, self.test_speaker):
            widget.setEnabled(idle)
        self.stop.setEnabled(c.audio_worker is not None)
        if c.demo:
            self.notice.setText('Démo · aucun périphérique n’est consulté ou ouvert.')
        elif c.voice_worker is not None:
            self.notice.setText('Arrêtez le vocal pour changer ou tester les périphériques.')
        elif c.device_config_invalid:
            self.notice.setText('Choix enregistré invalide. Sélectionnez à nouveau vos périphériques ou utilisez les périphériques système.')

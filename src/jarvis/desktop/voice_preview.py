"""Bounded Live voice audition: fixed text, no tools, no microphone, no files."""
import asyncio
import os
from threading import Event
from PySide6.QtCore import QThread, Signal
from jarvis.desktop.devices import AudioDeviceError, RATE, resolve_device
from jarvis.desktop.voices import VOICE_IDS

PREVIEW_TEXT = ('Bonjour, je suis Jarvis. Je peux vous aider à organiser votre journée. '
                'Quelle est votre prochaine idée ?')
MAX_BYTES = RATE * 2 * 15


async def collect_preview(session):
    await session.send_client_content(turns={'role': 'user', 'parts': [{'text': PREVIEW_TEXT}]}, turn_complete=True)
    pcm = bytearray()
    completed = False
    async for response in session.receive():
        content = response.server_content
        if content is None:
            continue
        if content.model_turn:
            for part in content.model_turn.parts or []:
                blob = part.inline_data
                if blob is None or not blob.data:
                    continue
                mime = (blob.mime_type or '').replace(' ', '').lower()
                fields = mime.split(';')
                rate = next((field.split('=', 1)[1] for field in fields[1:] if field.startswith('rate=')), '24000')
                if fields[0] != 'audio/pcm' or rate != '24000':
                    raise ValueError('Unsupported preview format')
                if len(pcm) + len(blob.data) > MAX_BYTES:
                    raise ValueError('Preview too long')
                pcm.extend(blob.data)
        if content.turn_complete:
            completed = True
            break
    if not completed or not pcm or len(pcm) % 2:
        raise ValueError('Empty or incomplete preview')
    return bytes(pcm)


async def generate_preview(voice, stopped, client_factory=None):
    from jarvis.desktop.live_runtime import prepare_environment
    from jarvis.live.config import get_live_config
    prepare_environment()
    if client_factory is None:
        from google import genai
        client_factory = genai.Client
    client = client_factory(api_key=os.environ['GOOGLE_API_KEY'])
    config = {'response_modalities': ['AUDIO'],
              'system_instruction': 'Lis uniquement le texte fourni, en français, naturellement. Aucun ajout.',
              'speech_config': {'voice_config': {'prebuilt_voice_config': {'voice_name': voice}}}}
    async def generate():
        async with client.aio.live.connect(model=get_live_config().model, config=config) as session:
            return await collect_preview(session)
    task = asyncio.create_task(asyncio.wait_for(generate(), 30))
    try:
        while not stopped.is_set():
            done, _ = await asyncio.wait({task}, timeout=.1)
            if done:
                return task.result()
        return None
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        try:
            await asyncio.wait_for(client.aio.aclose(), 3)
        finally:
            client.close()


def play_preview(pcm, choice, stopped, devices=None):
    if stopped.is_set():
        return
    if devices is None:
        import sounddevice as devices
    output = resolve_device(devices, choice, 'output')
    with devices.RawOutputStream(device=output, samplerate=RATE, channels=1, dtype='int16') as speaker:
        for offset in range(0, len(pcm), 2400):
            if stopped.is_set():
                speaker.abort()
                break
            speaker.write(pcm[offset:offset+2400])


class VoicePreview(QThread):
    event = Signal(object)

    def __init__(self, voice, output_choice=None, parent=None, generator=generate_preview, player=play_preview):
        super().__init__(parent)
        if voice not in VOICE_IDS:
            raise ValueError('Unknown voice')
        self.voice, self.output_choice = voice, output_choice
        self.stopped = Event()
        self.generator, self.player = generator, player

    def stop(self):
        self.stopped.set()

    def report(self, state, message):
        self.event.emit({'type': 'audio_test', 'kind': 'voice_preview', 'state': state, 'message': message})

    def run(self):
        from jarvis.desktop.live_runtime import VoiceSetupError
        try:
            if self.stopped.is_set():
                return
            self.report('preparing', f'Préparation de la voix {self.voice}… · micro fermé')
            pcm = asyncio.run(self.generator(self.voice, self.stopped))
            if pcm and not self.stopped.is_set():
                self.report('speaker', f'Écoute de {self.voice} · micro fermé')
                self.player(pcm, self.output_choice, self.stopped)
            self.report('done', 'Aperçu arrêté.' if self.stopped.is_set() else 'Aperçu terminé.')
        except VoiceSetupError:
            self.report('error', 'Aperçu indisponible. Vérifiez la clé Gemini et les dépendances vocales.')
        except AudioDeviceError as error:
            self.report('error', str(error))
        except Exception:
            if self.stopped.is_set():
                self.report('done', 'Aperçu arrêté.')
            else:
                self.report('error', 'Impossible de lire cette voix. Vérifiez la connexion, le modèle et le quota Gemini, puis réessayez.')

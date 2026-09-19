import queue
import tempfile
import wave

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel


class VoiceInput:
    def __init__(self):
        self.sample_rate = 16000

        # Reglages de detection vocale
        self.block_duration = 0.1
        self.silence_duration = 1.0
        self.max_duration = 20.0
        self.start_threshold = 0.015
        self.continue_threshold = 0.010

        print("Chargement du moteur vocal...")

        self.model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8",
        )

        print("Moteur vocal pret.")

    def _record_until_silence(self):
        audio_queue = queue.Queue()
        frames = []

        speech_started = False
        silence_time = 0.0
        total_time = 0.0

        def callback(indata, frames_count, time_info, status):
            if status:
                print(f"Audio : {status}")

            audio_queue.put(indata.copy())

        block_size = int(
            self.sample_rate * self.block_duration
        )

        print()
        print("🎙️ Je vous ecoute...")

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=block_size,
            callback=callback,
        ):
            while total_time < self.max_duration:
                block = audio_queue.get()

                samples = block.astype(np.float32) / 32768.0
                level = float(np.sqrt(np.mean(samples ** 2)))

                total_time += self.block_duration

                if not speech_started:
                    if level >= self.start_threshold:
                        speech_started = True
                        print("🗣️ Parole detectee...")
                        frames.append(block)
                    continue

                frames.append(block)

                if level < self.continue_threshold:
                    silence_time += self.block_duration
                else:
                    silence_time = 0.0

                if silence_time >= self.silence_duration:
                    break

        if not speech_started or not frames:
            return None

        return np.concatenate(frames, axis=0)

    def listen(self) -> str:
        audio = self._record_until_silence()

        if audio is None:
            return ""

        print("🧠 Analyse...")

        with tempfile.NamedTemporaryFile(suffix=".wav") as temp:
            with wave.open(temp.name, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.sample_rate)
                wav.writeframes(audio.tobytes())

            segments, _ = self.model.transcribe(
                temp.name,
                language="fr",
                beam_size=5,
                vad_filter=True,
                initial_prompt=(
                    "Jarvis, Safari, Spotify, YouTube, "
                    "macOS, ouvre, ferme, recherche, volume."
                ),
            )

            text = " ".join(
                segment.text.strip()
                for segment in segments
            ).strip()

        return text

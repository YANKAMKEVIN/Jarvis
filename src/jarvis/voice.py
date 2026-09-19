import tempfile
import wave

import sounddevice as sd
from faster_whisper import WhisperModel


class VoiceInput:
    def __init__(self):
        self.sample_rate = 16000

        print("Chargement du moteur vocal...")
        self.model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8",
        )
        print("Moteur vocal pret.")

    def listen(self, duration: int = 5) -> str:
        print()
        print("🎙️ Je vous ecoute...")

        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
        )

        sd.wait()

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

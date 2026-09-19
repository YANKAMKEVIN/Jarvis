import subprocess


class VoiceOutput:
    def __init__(self, voice: str = "Amélie", rate: int = 190):
        self.voice = voice
        self.rate = rate

    def speak(self, text: str) -> None:
        if not text or not text.strip():
            return

        subprocess.run(
            [
                "say",
                "-v",
                self.voice,
                "-r",
                str(self.rate),
                text,
            ],
            check=True,
        )

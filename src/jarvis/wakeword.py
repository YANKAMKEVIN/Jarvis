import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.voice import VoiceInput


class WakeWordDetector:
    def __init__(
        self,
        voice_input: "VoiceInput | None" = None,
        wake_word: str = "jarvis",
    ):
        self.wake_word = self._normalize(wake_word)

        if voice_input is None:
            from jarvis.voice import VoiceInput

            voice_input = VoiceInput()

        self.voice = voice_input

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower()

        text = "".join(
            char
            for char in unicodedata.normalize("NFD", text)
            if unicodedata.category(char) != "Mn"
        )

        text = re.sub(r"[^a-z0-9\s]", " ", text)

        return " ".join(text.split())

    def detect(self, text: str) -> bool:
        return any(
            self._normalize(match.group()) == self.wake_word
            for match in re.finditer(r"[^\W_]+", text, flags=re.UNICODE)
        )

    def extract_inline_command(self, text: str) -> str:
        """
        Extrait uniquement ce qui suit le wake word detecte comme mot.

        On s'appuie sur les bornes de mots de la transcription originale afin
        d'eviter de supprimer "Jarvis" lorsqu'il apparait dans un autre mot.
        """
        for match in re.finditer(r"[^\W_]+", text, flags=re.UNICODE):
            if self._normalize(match.group()) != self.wake_word:
                continue

            command = text[match.end():]
            command = re.sub(r"^[\s,;:!?.-]+", "", command)
            command = re.sub(r"\s+", " ", command).strip()

            if not re.search(r"[^\W_]", command, flags=re.UNICODE):
                return ""

            return command

        return ""

    def wait(self) -> str:
        """
        Attend qu'une phrase contenant le wake word soit prononcee.

        Retourne la transcription complete afin que Jarvis puisse
        ensuite distinguer :

        "Jarvis"
        de
        "Jarvis ouvre Safari"
        """
        print()
        print('💤 En attente de "Jarvis"...')

        while True:
            text = self.voice.listen()

            if not text:
                continue

            if self.detect(text):
                print(f"✨ Jarvis detecte : {text}")
                return text

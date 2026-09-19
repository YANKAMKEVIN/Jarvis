import re
import unicodedata
from enum import Enum


SESSION_TIMEOUT_SECONDS = 180
# Prepare pour une prochaine etape : VoiceInput.listen() est encore bloquant,
# donc la boucle vocale ne simule pas un timeout qui ne pourrait pas sonner.


EXIT_PHRASES = {
    "au revoir",
    "arrete toi",
    "c est tout",
    "c est tout pour aujourd hui",
    "on va s arreter la",
    "on s arrete la",
    "retourne en veille",
    "stop",
    "tu peux dormir",
    "va dormir",
    "quitte",
}


class SessionState(Enum):
    SLEEPING = "sleeping"
    ACTIVE = "active"


def normalize_text(text: str) -> str:
    """
    Normalise une phrase pour faciliter la detection
    des commandes vocales.
    """
    text = text.lower()

    # Retire les accents.
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )

    # Remplace la ponctuation par des espaces.
    text = re.sub(r"[^a-z0-9\s]", " ", text)

    # Supprime les espaces multiples.
    return " ".join(text.split())


def is_exit_command(command: str) -> bool:
    """
    Detecte une intention claire de terminer la session vocale active.

    On evite volontairement de quitter si l'utilisateur
    mentionne simplement l'expression "au revoir".
    """
    normalized = normalize_text(command)

    # Commandes exactes.
    if normalized in EXIT_PHRASES:
        return True

    # Formulations naturelles de fin de conversation.
    farewell_patterns = [
        r"^au revoir(?: jarvis)?$",
        r"^(?:merci|merci jarvis) au revoir(?: jarvis)?$",
        r"\bon va s arreter la(?: jarvis)?(?: au revoir)?$",
        r"\bon s arrete la(?: jarvis)?(?: au revoir)?$",
        r"\bc est tout(?: pour aujourd hui)?(?: jarvis)?(?: au revoir)?$",
        r"\btu peux dormir(?: jarvis)?$",
        r"\bretourne en veille(?: jarvis)?$",
        r"\bva dormir(?: jarvis)?$",
    ]

    if any(
        re.search(pattern, normalized)
        for pattern in farewell_patterns
    ):
        return True

    # Ordres explicites pour arreter Jarvis.
    stop_patterns = [
        r"^arrete toi(?: jarvis)?$",
        r"^jarvis arrete toi$",
        r"^quitte(?: jarvis)?$",
        r"^stop(?: jarvis)?$",
    ]

    return any(
        re.search(pattern, normalized)
        for pattern in stop_patterns
    )


def is_confirmation(command: str) -> bool:
    """
    Detecte une confirmation vocale simple.
    """
    normalized = normalize_text(command)

    return normalized in {
        "oui",
        "oui jarvis",
        "je confirme",
        "confirme",
    }


class VoiceMode:
    def __init__(
        self,
        executor=None,
        voice=None,
        wakeword=None,
        speech=None,
    ):
        if executor is None:
            from jarvis.executor import CommandExecutor

            executor = CommandExecutor()

        if voice is None:
            from jarvis.voice import VoiceInput

            voice = VoiceInput()

        if wakeword is None:
            from jarvis.wakeword import WakeWordDetector

            wakeword = WakeWordDetector(voice)

        if speech is None:
            from jarvis.speech import VoiceOutput

            speech = VoiceOutput()

        self.executor = executor
        self.voice = voice
        self.wakeword = wakeword
        self.speech = speech
        self.state = SessionState.SLEEPING

    def _speak(self, message: str) -> None:
        print(f"Jarvis > {message}")
        self.speech.speak(message)

    def _activate_from_wake_text(self, text: str) -> str:
        command = self.wakeword.extract_inline_command(text)
        self.state = SessionState.ACTIVE

        if not command:
            self._speak("Oui ?")

        return command

    def handle_sleeping_text(self, text: str) -> str:
        """
        Traite une transcription recue en veille.

        Retourne une commande inline si le wake word en contenait une,
        sinon une chaine vide. Cette methode garde la logique testable sans
        microphone; la boucle reelle utilise WakeWordDetector.wait().
        """
        if not text or not self.wakeword.detect(text):
            return ""

        return self._activate_from_wake_text(text)

    def _return_to_sleep(self) -> None:
        self.state = SessionState.SLEEPING
        self._speak("À bientôt.")

    def handle_active_command(self, command: str) -> None:
        if not command:
            return

        print(f"Vous > {command}")

        # Detection naturelle de fin de session.
        if is_exit_command(command):
            self._return_to_sleep()
            return

        # Envoi de la commande au moteur commun.
        result = self.executor.execute(command)

        # Gestion des actions necessitant une confirmation.
        if result.needs_confirmation:
            message = (
                "Cette action nécessite votre confirmation. "
                "Dites oui pour continuer."
            )

            self._speak(message)

            confirmation = self.voice.listen()

            if confirmation:
                print(f"Vous > {confirmation}")

            if not is_confirmation(confirmation):
                self._speak("Action annulée.")
                return

            result = self.executor.execute(
                command,
                confirmed=True,
            )

        # Reponse finale.
        self._speak(result.message)

    def run(self):
        print()
        print("=" * 45)
        print("JARVIS — MODE VOCAL")
        print("=" * 45)
        print('Dites "Jarvis" pour activer l ecoute.')
        print(
            "Timeout de session prepare : "
            f"{SESSION_TIMEOUT_SECONDS} secondes."
        )
        print("Ctrl+C pour quitter.")
        print()

        self.speech.speak("Mode vocal activé.")

        while True:
            try:
                if self.state == SessionState.SLEEPING:
                    wake_text = self.wakeword.wait()
                    command = self._activate_from_wake_text(wake_text)
                else:
                    command = self.voice.listen()

                # Si une fausse detection audio ne produit
                # aucun texte, Jarvis recommence simplement
                # selon l'etat courant.
                if not command:
                    continue

                self.handle_active_command(command)

            except KeyboardInterrupt:
                print()
                print("Jarvis > Mode vocal termine.")
                break

            except Exception as error:
                print()
                print("Jarvis > Je rencontre un probleme.")
                print(f"Erreur technique : {error}")
                print()


if __name__ == "__main__":
    VoiceMode().run()

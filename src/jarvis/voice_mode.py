import re
import unicodedata

from jarvis.executor import CommandExecutor
from jarvis.speech import VoiceOutput
from jarvis.voice import VoiceInput


EXIT_PHRASES = {
    "au revoir",
    "arrete toi",
    "on va s arreter la",
    "on s arrete la",
    "stop",
    "quitte",
}


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
    Detecte une intention claire de terminer Jarvis.

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
    def __init__(self):
        self.executor = CommandExecutor()
        self.voice = VoiceInput()
        self.speech = VoiceOutput()

    def run(self):
        print()
        print("=" * 45)
        print("JARVIS — MODE VOCAL")
        print("=" * 45)
        print("Dites votre commande lorsque Jarvis vous ecoute.")
        print("Ctrl+C pour quitter.")
        print()

        self.speech.speak("Mode vocal activé.")

        while True:
            try:
                command = self.voice.listen()

                # Si une fausse detection audio ne produit
                # aucun texte, Jarvis recommence simplement
                # a ecouter sans parler.
                if not command:
                    continue

                print(f"Vous > {command}")

                # Detection naturelle de fin de conversation.
                if is_exit_command(command):
                    message = "À bientôt."

                    print(f"Jarvis > {message}")
                    self.speech.speak(message)

                    break

                # Envoi de la commande au moteur commun.
                result = self.executor.execute(command)

                # Gestion des actions necessitant
                # une confirmation.
                if result.needs_confirmation:
                    message = (
                        "Cette action nécessite votre confirmation. "
                        "Dites oui pour continuer."
                    )

                    print(f"Jarvis > {message}")
                    self.speech.speak(message)

                    confirmation = self.voice.listen()

                    if confirmation:
                        print(f"Vous > {confirmation}")

                    if not is_confirmation(confirmation):
                        message = "Action annulée."

                        print(f"Jarvis > {message}")
                        self.speech.speak(message)

                        continue

                    result = self.executor.execute(
                        command,
                        confirmed=True,
                    )

                # Reponse finale.
                print(f"Jarvis > {result.message}")
                self.speech.speak(result.message)

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

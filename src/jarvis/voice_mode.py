from jarvis.executor import CommandExecutor
from jarvis.speech import VoiceOutput
from jarvis.voice import VoiceInput


EXIT_COMMANDS = {
    "au revoir",
    "arrête-toi",
    "arrete-toi",
    "stop",
    "quitte",
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

                if not command:
                    print("Jarvis > Je n'ai rien entendu.")
                    continue

                print(f"Vous > {command}")

                normalized = command.lower().strip().rstrip(".!?")

                if normalized in EXIT_COMMANDS:
                    message = "À bientôt."
                    print(f"Jarvis > {message}")
                    self.speech.speak(message)
                    break

                result = self.executor.execute(command)

                if result.needs_confirmation:
                    message = (
                        "Cette action nécessite votre confirmation. "
                        "Dites oui pour continuer."
                    )

                    print(f"Jarvis > {message}")
                    self.speech.speak(message)

                    confirmation = self.voice.listen()
                    print(f"Vous > {confirmation}")

                    if confirmation.lower().strip().rstrip(".!?") not in {
                        "oui",
                        "oui jarvis",
                        "je confirme",
                        "confirme",
                    }:
                        message = "Action annulée."
                        print(f"Jarvis > {message}")
                        self.speech.speak(message)
                        continue

                    result = self.executor.execute(
                        command,
                        confirmed=True,
                    )

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

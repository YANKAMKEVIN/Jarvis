from datetime import datetime

from jarvis.brain import Brain
from jarvis.intents import create_intent
from jarvis.security import SecurityManager
from jarvis.tools.macos import MacOSTools


def start_jarvis():
    print()
    print("=" * 45)
    print("JARVIS")
    print("Personal AI Assistant")
    print("=" * 45)
    print("Systeme : operationnel")
    print("Cerveau : local")
    print("Securite : active")
    print()

    brain = Brain()
    security = SecurityManager()
    tools = MacOSTools()

    while True:
        command = input("Vous > ").strip()

        if not command:
            continue

        if command.lower() in {"quit", "exit", "stop", "au revoir"}:
            print("Jarvis > A bientot.")
            break

        if "heure" in command.lower():
            current_time = datetime.now().strftime("%H:%M")
            print(f"Jarvis > Il est {current_time}.")
            continue

        try:
            detected = brain.detect_intent(command)

            action = detected.get("action", "conversation")
            target = detected.get("target")

            # Conversation normale
            if action == "conversation":
                answer = brain.think(command)
                print(f"\nJarvis > {answer}\n")
                continue

            # Création de l'intention sécurisée
            intent = create_intent(action, target)
            decision = security.evaluate(intent)

            if not decision.allowed:
                print(
                    "\nJarvis > Je ne suis pas autorise "
                    "a effectuer cette action.\n"
                )
                continue

            if decision.requires_confirmation:
                confirmation = input(
                    "Jarvis > Cette action necessite votre confirmation. "
                    "Continuer ? (oui/non) "
                ).strip().lower()

                if confirmation not in {"oui", "o", "yes", "y"}:
                    print("Jarvis > Action annulee.")
                    continue

            # Exécution des outils autorisés
            if intent.action == "open_app":
                if not intent.target:
                    print("Jarvis > Quelle application dois-je ouvrir ?")
                    continue

                result = tools.open_app(intent.target)
                print(f"Jarvis > {result}")
                continue

            if intent.action == "close_app":
                if not intent.target:
                    print("Jarvis > Quelle application dois-je fermer ?")
                    continue

                result = tools.close_app(intent.target)
                print(f"Jarvis > {result}")
                continue

            if intent.action == "open_url":
                if not intent.target:
                    print("Jarvis > Quel site dois-je ouvrir ?")
                    continue

                result = tools.open_url(intent.target)
                print(f"Jarvis > {result}")
                continue

            if intent.action == "web_search":
                if not intent.target:
                    print("Jarvis > Que dois-je rechercher ?")
                    continue

                result = tools.web_search(intent.target)
                print(f"Jarvis > {result}")
                continue

            if intent.action == "get_date":
                result = tools.get_date()
                print(f"Jarvis > Nous sommes le {result}.")
                continue

            if intent.action == "set_volume":
                if intent.target is None:
                    print("Jarvis > A quel niveau dois-je regler le volume ?")
                    continue

                try:
                    level = int(intent.target)
                except (TypeError, ValueError):
                    print("Jarvis > Je n'ai pas compris le niveau du volume.")
                    continue

                result = tools.set_volume(level)
                print(f"Jarvis > {result}")
                continue

            if intent.action == "mute":
                result = tools.mute()
                print(f"Jarvis > {result}")
                continue

            if intent.action == "unmute":
                result = tools.unmute()
                print(f"Jarvis > {result}")
                continue

            print("Jarvis > Cette action n'est pas encore disponible.")

        except Exception as error:
            print()
            print("Jarvis > Je rencontre un probleme.")
            print(f"Erreur technique : {error}")
            print()


if __name__ == "__main__":
    start_jarvis()

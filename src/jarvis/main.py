from datetime import datetime

from jarvis.brain import Brain


def start_jarvis():
    print()
    print("=" * 45)
    print("JARVIS")
    print("Personal AI Assistant")
    print("=" * 45)
    print("Systeme : operationnel")
    print("Mode : IA connectee")
    print("Securite : active")
    print()

    brain = Brain()

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
            answer = brain.think(command)
            print(f"\nJarvis > {answer}\n")

        except Exception as error:
            print()
            print("Jarvis > Je rencontre un probleme avec mon cerveau IA.")
            print(f"Erreur technique : {error}")
            print()


if __name__ == "__main__":
    start_jarvis()

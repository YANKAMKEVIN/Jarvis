from datetime import datetime

from jarvis.executor import CommandExecutor


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

    executor = CommandExecutor()

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
            result = executor.execute(command)

            if result.needs_confirmation:
                confirmation = input(
                    "Jarvis > Cette action necessite votre confirmation. "
                    "Continuer ? (oui/non) "
                ).strip().lower()

                if confirmation not in {"oui", "o", "yes", "y"}:
                    print("Jarvis > Action annulee.")
                    continue

                result = executor.execute(
                    command,
                    confirmed=True,
                )

            print(f"\nJarvis > {result.message}\n")

        except Exception as error:
            print()
            print("Jarvis > Je rencontre un probleme.")
            print(f"Erreur technique : {error}")
            print()


if __name__ == "__main__":
    start_jarvis()

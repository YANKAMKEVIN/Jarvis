from jarvis.executor import CommandExecutor


CONFIRMATION_PROMPT = (
    "Jarvis > Cette action necessite votre confirmation. "
    "Continuer ? (oui/non) "
)


def respond(executor, command: str, ask=input) -> str:
    """One REPL turn: run the command, ask for confirmation if needed.

    After a "oui", the exact previewed intent is executed: the model never
    reads the sentence again, so it cannot pick another action.
    """
    result = executor.execute(command)

    if result.needs_confirmation:
        confirmation = ask(CONFIRMATION_PROMPT).strip().lower()

        if confirmation not in {"oui", "o", "yes", "y"}:
            return "Action annulee."

        if result.intent is None:
            return "Action annulee : aucune action precise a confirmer."

        result = executor.execute_intent(result.intent, confirmed=True)

    return result.message


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

        try:
            message = respond(executor, command)
            print(f"\nJarvis > {message}\n")

        except Exception as error:
            print()
            print("Jarvis > Je rencontre un probleme.")
            print(f"Erreur technique : {error}")
            print()


def cli(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Jarvis en mode texte.")
    parser.add_argument(
        "--outils", action="store_true",
        help="utiliser le planificateur et tous les outils de Jarvis (memoire, notes, rappels...)",
    )
    args = parser.parse_args(argv)
    if args.outils:
        from jarvis.text_agent import start_text_agent
        start_text_agent()
    else:
        start_jarvis()


if __name__ == "__main__":
    cli()

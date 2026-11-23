"""Text and voice modes confirm the exact previewed intent (idea 5)."""
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace as NS

from jarvis.intents import create_intent
from jarvis.main import respond
from jarvis.voice_mode import VoiceMode
from jarvis.wakeword import WakeWordDetector


class Executor:
    """execute() previews; a second execute() would detect another action."""

    def __init__(self):
        self.calls = []

    def execute(self, command, confirmed=False):
        self.calls.append(("execute", command, confirmed))
        if confirmed:
            return NS(message="AUTRE ACTION", needs_confirmation=False, intent=None)
        return NS(message="Confirmer ?", needs_confirmation=True, intent=create_intent("close_app", "Notes"))

    def execute_intent(self, intent, confirmed=False):
        self.calls.append(("execute_intent", intent.action, intent.target, confirmed))
        return NS(message=f"{intent.action}:{intent.target}", needs_confirmation=False, intent=intent)


def test_text_mode_runs_the_previewed_intent_after_yes():
    executor = Executor()
    assert respond(executor, "ferme Notes", ask=lambda prompt: "oui") == "close_app:Notes"
    assert executor.calls == [("execute", "ferme Notes", False), ("execute_intent", "close_app", "Notes", True)]


def test_text_mode_cancels_on_no_and_without_intent():
    executor = Executor()
    assert respond(executor, "ferme Notes", ask=lambda prompt: "non") == "Action annulee."
    assert len(executor.calls) == 1

    class NoIntent(Executor):
        def execute(self, command, confirmed=False):
            return NS(message="?", needs_confirmation=True, intent=None)
    assert "aucune action" in respond(NoIntent(), "x", ask=lambda prompt: "oui")


class Voice:
    def __init__(self, answers): self.answers = list(answers)
    def listen(self): return self.answers.pop(0) if self.answers else ""


class Speech:
    def __init__(self): self.said = []
    def speak(self, text): self.said.append(text)


def test_voice_mode_runs_the_previewed_intent_after_yes():
    executor, voice, speech = Executor(), Voice(["oui"]), Speech()
    mode = VoiceMode(executor=executor, voice=voice, wakeword=WakeWordDetector(voice), speech=speech)
    with redirect_stdout(StringIO()):
        mode.handle_active_command("ferme Notes")
    assert executor.calls[-1] == ("execute_intent", "close_app", "Notes", True)
    assert not any(call[0] == "execute" and call[2] for call in executor.calls)
    assert speech.said[-1] == "close_app:Notes"

import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace

from jarvis.voice_mode import SessionState, VoiceMode, is_exit_command
from jarvis.wakeword import WakeWordDetector


class FakeVoiceInput:
    def __init__(self, responses=None):
        self.responses = list(responses or [])

    def listen(self):
        if not self.responses:
            return ""

        return self.responses.pop(0)


class FakeSpeech:
    def __init__(self):
        self.messages = []

    def speak(self, text):
        self.messages.append(text)


class FakeExecutor:
    def __init__(self):
        self.commands = []

    def execute(self, command, confirmed=False):
        self.commands.append((command, confirmed))
        return SimpleNamespace(
            message=f"execute: {command}",
            needs_confirmation=False,
        )


def make_voice_mode():
    voice = FakeVoiceInput()
    wakeword = WakeWordDetector(voice)
    executor = FakeExecutor()
    speech = FakeSpeech()

    mode = VoiceMode(
        executor=executor,
        voice=voice,
        wakeword=wakeword,
        speech=speech,
    )

    return mode, executor, speech


def silently(callback, *args):
    with redirect_stdout(StringIO()):
        return callback(*args)


class WakeWordDetectorTest(unittest.TestCase):
    def test_detects_jarvis(self):
        detector = WakeWordDetector(FakeVoiceInput())

        self.assertTrue(detector.detect("Jarvis"))
        self.assertTrue(detector.detect("Salut Jarvis, tu es la ?"))

    def test_does_not_detect_j_arrive(self):
        detector = WakeWordDetector(FakeVoiceInput())

        self.assertFalse(detector.detect("J'arrive"))

    def test_extracts_inline_command(self):
        detector = WakeWordDetector(FakeVoiceInput())

        self.assertEqual(
            detector.extract_inline_command("Jarvis, ouvre Safari"),
            "ouvre Safari",
        )
        self.assertEqual(
            detector.extract_inline_command("Jarvis mets le volume a 30%"),
            "mets le volume a 30%",
        )

    def test_extracts_no_inline_command_when_only_wake_word(self):
        detector = WakeWordDetector(FakeVoiceInput())

        self.assertEqual(detector.extract_inline_command("Jarvis"), "")
        self.assertEqual(detector.extract_inline_command("Jarvis !"), "")

    def test_reuses_injected_voice_input(self):
        voice = FakeVoiceInput()
        detector = WakeWordDetector(voice)

        self.assertIs(detector.voice, voice)


class ExitCommandTest(unittest.TestCase):
    def test_detects_exit_commands(self):
        self.assertTrue(is_exit_command("Au revoir"))
        self.assertTrue(is_exit_command("Merci Jarvis, au revoir"))
        self.assertTrue(
            is_exit_command("On va s'arrêter là, au revoir")
        )
        self.assertTrue(is_exit_command("C'est tout"))
        self.assertTrue(is_exit_command("C'est tout pour aujourd'hui"))
        self.assertTrue(is_exit_command("Tu peux dormir"))
        self.assertTrue(is_exit_command("Retourne en veille"))
        self.assertTrue(is_exit_command("Va dormir"))

    def test_does_not_exit_on_farewell_question(self):
        self.assertFalse(
            is_exit_command("Comment dit-on au revoir en japonais ?")
        )
        self.assertFalse(
            is_exit_command("Que signifie l'expression au revoir ?")
        )
        self.assertFalse(is_exit_command("Explique-moi le sommeil"))
        self.assertFalse(is_exit_command("Pourquoi doit-on dormir ?"))


class VoiceModeSessionTest(unittest.TestCase):
    def test_initial_state_is_sleeping(self):
        mode, _, _ = make_voice_mode()

        self.assertEqual(mode.state, SessionState.SLEEPING)

    def test_ambient_speech_in_sleeping_is_ignored(self):
        mode, executor, speech = make_voice_mode()

        command = silently(
            mode.handle_sleeping_text,
            "Bonjour, tu vas bien ?",
        )

        self.assertEqual(command, "")
        self.assertEqual(mode.state, SessionState.SLEEPING)
        self.assertEqual(executor.commands, [])
        self.assertEqual(speech.messages, [])

    def test_wake_word_opens_active_session_and_acknowledges(self):
        mode, _, speech = make_voice_mode()

        command = silently(mode.handle_sleeping_text, "Jarvis")

        self.assertEqual(command, "")
        self.assertEqual(mode.state, SessionState.ACTIVE)
        self.assertEqual(speech.messages, ["Oui ?"])

    def test_inline_wake_command_executes_without_acknowledgement(self):
        mode, executor, speech = make_voice_mode()

        command = silently(
            mode.handle_sleeping_text,
            "Jarvis, ouvre Safari",
        )
        silently(mode.handle_active_command, command)

        self.assertEqual(mode.state, SessionState.ACTIVE)
        self.assertEqual(executor.commands, [("ouvre Safari", False)])
        self.assertEqual(speech.messages, ["execute: ouvre Safari"])

    def test_active_session_accepts_commands_without_wake_word(self):
        mode, executor, _ = make_voice_mode()
        silently(mode.handle_sleeping_text, "Jarvis")

        silently(mode.handle_active_command, "ouvre Safari")
        silently(mode.handle_active_command, "mets le volume a 30%")

        self.assertEqual(mode.state, SessionState.ACTIVE)
        self.assertEqual(
            executor.commands,
            [
                ("ouvre Safari", False),
                ("mets le volume a 30%", False),
            ],
        )

    def test_farewell_question_does_not_close_active_session(self):
        mode, executor, _ = make_voice_mode()
        silently(mode.handle_sleeping_text, "Jarvis")

        silently(
            mode.handle_active_command,
            "Comment dit-on au revoir en japonais ?",
        )

        self.assertEqual(mode.state, SessionState.ACTIVE)
        self.assertEqual(
            executor.commands,
            [("Comment dit-on au revoir en japonais ?", False)],
        )

    def test_exit_command_returns_to_sleeping_without_stopping_process(self):
        mode, executor, speech = make_voice_mode()
        silently(mode.handle_sleeping_text, "Jarvis")
        speech.messages.clear()

        silently(mode.handle_active_command, "Au revoir")

        self.assertEqual(mode.state, SessionState.SLEEPING)
        self.assertEqual(executor.commands, [])
        self.assertEqual(speech.messages, ["À bientôt."])


if __name__ == "__main__":
    unittest.main()

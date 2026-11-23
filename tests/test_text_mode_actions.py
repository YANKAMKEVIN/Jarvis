"""Text routing recognises actions the executor can run (idea 7)."""
from types import SimpleNamespace as NS

import pytest

from jarvis.capabilities.results import ToolResult
from jarvis.executor import CommandExecutor
from jarvis.routing import RequestRouter, RequestType
from jarvis.security import SecurityManager


@pytest.mark.parametrize("text", [
    "Verrouille l'écran", "Verrouille le Mac", "Baisse la luminosité", "Mets la luminosité à 40 %",
    "Mets en pause", "Mets la musique en pause", "Reprends la musique", "Passe au morceau suivant",
    "Morceau précédent", "Minimise la fenêtre", "Réduis la fenêtre de Safari",
])
def test_supported_actions_route_to_action(text):
    assert RequestRouter().classify(text).request_type == RequestType.ACTION


@pytest.mark.parametrize("text", [
    "Explique-moi la luminosité d'une étoile", "La pause déjeuner dure combien ?",
    "Pourquoi l'écran se verrouille tout seul ?",
])
def test_lookalike_sentences_stay_out_of_actions(text):
    assert RequestRouter().classify(text).request_type != RequestType.ACTION


class Brain:
    def __init__(self, detected): self.detected = detected
    def route_request(self, text): return RequestRouter().classify(text)
    def detect_intent(self, text): return self.detected
    def think(self, text): return "conversation"


class Capability:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        def call(*args):
            self.calls.append((name, args))
            return ToolResult.success(action=name, message=f"{name} ok")
        return call


def run(text, detected):
    system, media, windows = Capability(), Capability(), Capability()
    executor = CommandExecutor(brain=Brain(detected), security=SecurityManager(), tools=NS(),
                               knowledge_service=NS(),
                               capabilities={"system": system, "media": media, "windows": windows})
    return executor.execute(text), system, media, windows


def test_lock_screen_runs_the_system_capability():
    result, system, media, windows = run("Verrouille l'écran", {"action": "lock_screen", "target": None})
    assert result.message == "lock_screen ok" and system.calls == [("lock_screen", ())]


def test_brightness_needs_a_level_and_passes_it_as_int():
    result, system, *_ = run("Baisse la luminosité", {"action": "set_brightness", "target": None})
    assert "niveau" in result.message and system.calls == []
    result, system, *_ = run("Mets la luminosité à 40", {"action": "set_brightness", "target": "40"})
    assert system.calls == [("set_brightness", (40,))]


def test_media_and_window_actions():
    result, _, media, _ = run("Mets en pause", {"action": "play_pause", "target": None})
    assert media.calls == [("play_pause", ())]
    result, _, _, windows = run("Minimise la fenêtre de Safari", {"action": "minimize_window", "target": "Safari"})
    assert windows.calls == [("minimize_window", ("Safari",))]

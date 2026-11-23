"""« heure » no longer short-circuits a whole sentence (idea 6)."""
from types import SimpleNamespace as NS

import pytest

from jarvis.executor import CommandExecutor
from jarvis.routing import RequestRouter, RequestType, is_time_question
from jarvis.security import SecurityManager


@pytest.mark.parametrize("text", [
    "Quelle heure est-il ?", "quelle heure il est", "Il est quelle heure ?", "Donne-moi l'heure",
    "Tu peux me dire quelle heure il est ?", "Tu as l'heure ?", "L'heure, s'il te plaît",
])
def test_time_questions(text):
    assert is_time_question(text)
    assert RequestRouter().classify(text).request_type == RequestType.ACTION


@pytest.mark.parametrize("text", [
    "Ouvre Notes dans une heure", "24 heures chrono", "Rappelle-moi dans une heure",
    "À quelle heure ferme la poste ?", "Quelle heure est-il à Tokyo ?",
])
def test_sentences_mentioning_heure_keep_their_route(text):
    assert not is_time_question(text)


class Brain:
    def __init__(self): self.calls = []
    def route_request(self, text):
        self.calls.append(text)
        return RequestRouter().classify(text)
    def detect_intent(self, text):
        self.calls.append(text)
        return {"action": "open_app", "target": "Notes"}
    def think(self, text):
        self.calls.append(text)
        return "conversation"


class Tools:
    def get_time(self): return "09:41"
    def open_app(self, name): return f"{name} ouverte."


def executor(brain):
    return CommandExecutor(brain=brain, security=SecurityManager(), tools=Tools(), knowledge_service=NS())


def test_time_question_is_answered_locally_without_the_model():
    brain = Brain()
    result = executor(brain).execute("Quelle heure est-il ?")
    assert result.message == "Il est 09:41."
    assert result.intent.action == "get_time"
    assert brain.calls == []


def test_open_in_an_hour_is_not_answered_with_the_time():
    brain = Brain()
    result = executor(brain).execute("Ouvre Notes dans une heure")
    assert result.message == "Notes ouverte."
    assert brain.calls

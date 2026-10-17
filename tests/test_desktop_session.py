from types import SimpleNamespace

import pytest

from jarvis.desktop.session import DesktopSession
from jarvis.executor import CommandExecutor
from jarvis.intents import Intent, RiskLevel
from jarvis.security import SecurityDecision


def response(message="Réponse", **kwargs):
    return SimpleNamespace(message=message, needs_confirmation=False, intent=None, **kwargs)


def test_draft_and_turn_survive_a_view_switch():
    # Both views hold the same session; clearing a turn must not reuse an ID.
    session = DesktopSession()
    session.draft = "mon brouillon"
    first = session.begin(session.draft)
    assert session.draft == ""
    with pytest.raises(ValueError):
        session.begin("doublon")
    session.finish(first, response())
    session.clear()
    second = session.begin("nouvelle demande")
    assert not session.finish(first, response())
    assert session.busy and second.id != first.id


def test_confirmation_freezes_target_and_is_single_use():
    session = DesktopSession()
    job = session.begin("ouvre Safari")
    intent = Intent("open_app", "Safari")
    session.finish(job, SimpleNamespace(message="Confirmer", needs_confirmation=True, intent=intent))
    intent.target = "Terminal"
    with pytest.raises(ValueError):
        session.begin("autre demande")
    confirmed = session.confirm()
    assert confirmed.intent.target == "Safari"
    with pytest.raises(ValueError):
        session.confirm()
    session.finish(confirmed, response())
    assert session.turns[-1].status == "response"  # Not a fabricated success.


def test_cancel_does_not_execute_and_running_cannot_be_cleared():
    session = DesktopSession()
    job = session.begin("action")
    with pytest.raises(ValueError):
        session.cancel()
    with pytest.raises(ValueError):
        session.clear()
    session.finish(job, SimpleNamespace(message="Confirmer", needs_confirmation=True, intent=Intent("open_app", "Safari")))
    session.cancel()
    assert session.pending is None
    assert session.turns[-1].status == "cancelled"
    with pytest.raises(ValueError):
        session.confirm()


def test_worker_error_releases_session_without_claiming_rollback():
    session = DesktopSession()
    job = session.begin("action")
    session.finish(job, error="Erreur, vérifiez le résultat.")
    assert not session.busy
    assert session.turns[-1].status == "error"
    session.begin("suite")


def test_approved_intent_never_calls_model_again():
    class NoBrain:
        def __getattr__(self, name):
            raise AssertionError("Do not reinterpret an approved action")

    class Security:
        def evaluate(self, intent):
            return SecurityDecision(True, True, "confirmation")

    class Tools:
        calls = []
        def open_app(self, name):
            self.calls.append(name)
            return "Commande exécutée"

    tools = Tools()
    executor = CommandExecutor(brain=NoBrain(), security=Security(), tools=tools, knowledge_service=object())
    preview = executor.execute_intent(Intent("open_app", "Safari"))
    assert preview.needs_confirmation and tools.calls == []
    executor.execute_intent(preview.intent, confirmed=True)
    assert tools.calls == ["Safari"]


def test_crafted_intent_cannot_downgrade_unknown_action():
    executor = CommandExecutor(brain=object(), tools=object(), knowledge_service=object())
    result = executor.execute_intent(Intent("run_arbitrary_shell", "rm", RiskLevel.SAFE), confirmed=True)
    assert "pas autorisee" in result.message

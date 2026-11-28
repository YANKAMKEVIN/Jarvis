"""Pure logic of the text pipeline: routing -> intent -> security decision."""
import unicodedata

import pytest
from hypothesis import given, strategies as st

from jarvis.intents import ALLOWED_ACTIONS, Intent, RiskLevel, create_intent
from jarvis.routing import RequestRouter, RequestType, normalize_text
from jarvis.security import SecurityManager

ROUTER = RequestRouter()


# --- normalize_text -------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("Ouvre SAFARI !", "ouvre safari"),
    ("Règle le volume à 30 %", "regle le volume a 30 %"),
    ("  plusieurs\t espaces\n", "plusieurs espaces"),
    ("aide-moi", "aide moi"),
    ("youtube.com", "youtube com"),
    ("", ""),
    ("?!…", ""),
])
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected


@given(st.text())
def test_normalize_text_is_idempotent_and_ascii_safe(text):
    once = normalize_text(text)
    assert normalize_text(once) == once
    assert once == once.strip()
    assert "  " not in once
    assert all(not unicodedata.combining(char) for char in once)


# --- RequestRouter ----------------------------------------------------------

@pytest.mark.parametrize("message, expected", [
    ("Ouvre Safari", RequestType.ACTION),
    ("Lance Spotify", RequestType.ACTION),
    ("Ferme Mail", RequestType.ACTION),
    ("Coupe le son", RequestType.ACTION),
    ("Recherche des recettes de crêpes", RequestType.ACTION),
    ("Va sur youtube.com", RequestType.ACTION),
    # The top-level domain used to be matched as a literal ".com", which
    # normalization had already removed: these went to conversation.
    ("Va youtube.com", RequestType.ACTION),
    ("Va lemonde.fr", RequestType.ACTION),
    ("Quelle date sommes-nous ?", RequestType.ACTION),
    ("Quel temps fait-il demain ?", RequestType.KNOWLEDGE),
    ("Qui a gagné le match hier ?", RequestType.KNOWLEDGE),
    ("Quel est le prix du bitcoin", RequestType.KNOWLEDGE),
    ("Comment dit-on merci en japonais", RequestType.KNOWLEDGE),
    ("Aide-moi à écrire une lettre", RequestType.CONVERSATION),
    ("Résume ce texte", RequestType.CONVERSATION),
    ("Reformule cette phrase", RequestType.CONVERSATION),
    ("Raconte une blague", RequestType.CONVERSATION),
    ("Va dormir", RequestType.CONVERSATION),
    ("", RequestType.CONVERSATION),
    ("!!!", RequestType.CONVERSATION),
])
def test_router_classifies(message, expected):
    assert ROUTER.classify(message).request_type is expected


def test_action_wins_over_knowledge_words():
    # "aujourd'hui" is a knowledge marker, but an explicit command stays local.
    assert ROUTER.classify("Ouvre le calendrier d'aujourd'hui").request_type is RequestType.ACTION


@given(st.text())
def test_router_is_total_and_explains_itself(message):
    decision = ROUTER.classify(message)
    assert isinstance(decision.request_type, RequestType)
    assert decision.reason


# --- Intents and security ---------------------------------------------------

def test_known_actions_take_their_registered_risk():
    for action, risk in ALLOWED_ACTIONS.items():
        intent = create_intent(action, "cible")
        assert (intent.action, intent.target, intent.risk) == (action, "cible", risk)


@given(st.text().filter(lambda action: action not in ALLOWED_ACTIONS))
def test_unknown_actions_are_dangerous_and_blocked(action):
    intent = create_intent(action)
    assert intent.risk is RiskLevel.DANGEROUS
    decision = SecurityManager().evaluate(intent)
    assert not decision.allowed and not decision.requires_confirmation


def test_destructive_looking_actions_are_not_allowlisted():
    for action in ("delete_file", "empty_trash", "shutdown", "run_shell", "send_email"):
        assert create_intent(action).risk is RiskLevel.DANGEROUS


@pytest.mark.parametrize("risk, allowed, confirm", [
    (RiskLevel.SAFE, True, False),
    (RiskLevel.CONFIRM, True, True),
    (RiskLevel.DANGEROUS, False, False),
])
def test_security_decision_per_risk(risk, allowed, confirm):
    decision = SecurityManager().evaluate(Intent("x", risk=risk))
    assert (decision.allowed, decision.requires_confirmation) == (allowed, confirm)
    assert decision.reason


def test_executor_recomputes_risk_from_registry():
    """A hand-crafted SAFE intent for an unknown action is still blocked."""
    from jarvis.executor import CommandExecutor

    class Tools:
        def __getattr__(self, name):
            raise AssertionError(f"no system tool may run, got {name}")

    executor = CommandExecutor(brain=object(), tools=Tools(), knowledge_service=object())
    result = executor.execute_intent(Intent("delete_everything", risk=RiskLevel.SAFE))
    assert result.intent.risk is RiskLevel.DANGEROUS
    assert not result.needs_confirmation
    assert "autorisee" in result.message

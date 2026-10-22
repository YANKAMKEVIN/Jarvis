"""Opt-in real Ollama and web checks. Synthetic facts are never real news.

JARVIS_RUN_LIVE_TESTS=1 python -m pytest tests/test_live_answer_quality.py -q
A failure is a failure: unavailable dependencies are not converted to skips once
this suite has explicitly been enabled.
"""
import os
from datetime import date
import unicodedata
import pytest
from jarvis.brain import LocalBrain
from jarvis.knowledge.models import SearchMode,SearchResult
from jarvis.knowledge.keyless import FallbackProvider,KeylessWebProvider
from jarvis.knowledge.searxng import SearXNGProvider
from jarvis.knowledge.service import KnowledgeService

pytestmark=[pytest.mark.live,pytest.mark.skipif(os.environ.get('JARVIS_RUN_LIVE_TESTS')!='1',reason='Explicit real-service opt-in required')]

CASES=[
    ('sport_single_source','Donne des infos sur la finale des playoffs WNBA.',
     'La finale WNBA se joue au meilleur des sept matchs. La première équipe à quatre victoires remporte le titre.',('finale',)),
    ('deadline','Quelle est la date limite ?',
     'La date limite de dépôt du dossier est le 5 novembre 2026.',('5','novembre','2026')),
    ('price','Quel est le prix indiqué ?',
     'Le tarif du billet est de 42 euros. Le tarif réduit est de 28 euros.',('42','28')),
    ('opening','À quelle heure ouvre la bibliothèque ?',
     'La bibliothèque ouvre à 9 heures du lundi au vendredi.',('9',)),
    ('partial','Quelle équipe gagne et quel est le score ?',
     'Dans cet exemple fictif, les Comètes remportent le match. Aucun score n’est fourni.',('cometes',)),
    ('unknown','Quel est le code secret du projet ?',
     'Le projet est décrit publiquement, mais aucun code secret ne figure dans cet extrait.',()),
]

def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.casefold()) if not unicodedata.combining(c))

@pytest.mark.parametrize('name,question,evidence,expected',CASES,ids=[row[0] for row in CASES])
def test_real_local_model_answers_clear_evidence_without_blanket_refusal(name,question,evidence,expected):
    source=SearchResult('Extrait de test fictif','https://fixture.example/evidence',evidence)
    if name=='sport_single_source':
        source=SearchResult('WNBA : format des finales 2026','https://www.wnba.com/webview/news/2026-wnba-postseason-faq',evidence)
    text=LocalBrain().answer_from_sources(question,[source],search_mode=SearchMode.GENERAL,current_date=date(2026,10,22))
    value=normalize(text)
    assert value.strip()
    for term in expected:assert term in value
    if expected:assert not any(refusal in value for refusal in ('sources insuffisantes','pas suffisamment d','ne peux pas repondre'))
    if name=='sport_single_source':
        assert any(word in value for word in ('sept','7'))
        assert any(word in value for word in ('quatre','4'))
    if name=='partial':assert any(word in value for word in ('score','fourni','precis','indiqu'))
    if name=='unknown':assert any(word in value for word in ('aucun','pas','inconnu','absent'))

@pytest.mark.parametrize('question,topic',[
    ('Donne des infos sur la finale des playoffs WNBA','wnba'),
    ('Quelle est la capitale du Japon ?','japon'),
    ('Comment fonctionne la photosynthèse ?','photosynth'),
])
def test_real_search_to_real_synthesis_has_relevant_sources_and_a_usable_answer(question,topic):
    provider=FallbackProvider(SearXNGProvider(),KeylessWebProvider())
    answer=KnowledgeService(LocalBrain(),provider).answer(question)
    assert answer.failure_reason is None
    assert answer.external_knowledge_retrieved and answer.sources and answer.message.strip()
    assert any(topic in normalize(source.title+' '+source.url) for source in answer.sources)
    assert not any(term in normalize(answer.message) for term in ('sources insuffisantes','pas suffisamment d','ne peux pas repondre'))

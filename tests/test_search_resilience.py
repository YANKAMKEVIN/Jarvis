"""User-facing search contracts, including the reported WNBA false refusal."""
import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock
import urllib.error

import pytest

from jarvis.capabilities.knowledge import KnowledgeCapability, web_announcement_for
from jarvis.knowledge.keyless import KeylessWebProvider, FallbackProvider
from jarvis.knowledge.models import SearchMode, SearchResult
from jarvis.knowledge.searxng import SearXNGError
from jarvis.knowledge.service import KnowledgeService

NEWS_REQUESTS = [
    'donne des infos sur la finale des playoffs wnba',
    'Donne-moi des infos sur la finale WNBA',
    'Qui mène la finale WNBA ?',
    'Quel est le score du match NBA ?',
    'Résultats des playoffs NBA',
    'Classement de Ligue 1',
    'Les résultats de Wimbledon',
    'Qui a gagné la finale de Roland Garros ?',
    'Des nouvelles du Tour de France',
    'Les derniers résultats de NFL',
    'Quoi de neuf chez Apple ?',
    'Quelles sont les actualités IA aujourd’hui ?',
    'Les dernières nouvelles en France',
    'Que s’est-il passé aujourd’hui ?',
    'Les actualités spatiales',
]
GENERAL_REQUESTS = [
    'Comment fonctionnent les playoffs WNBA ?',
    'Quelles sont les règles de la finale NBA ?',
    'Quel est le format des playoffs NBA ?',
    'Histoire de la WNBA',
    'Qui a gagné la finale WNBA en 2019 ?',
    'Résultats de Wimbledon en 2008',
    'Quelle était la finale NBA en 1998 ?',
    'Pourquoi le ciel est bleu ?',
    'Comment faire une omelette ?',
    'Définition de la photosynthèse',
    'Qui est le président actuel de la France ?',
    'Comment dit-on bonjour en japonais ?',
    'Quelle est la capitale du Japon ?',
    'Comment calculer un pourcentage ?',
    'Quelle est la différence entre météo et climat ?',
]

@pytest.mark.parametrize('question', NEWS_REQUESTS)
def test_recent_user_requests_use_news(question):
    assert KnowledgeService.detect_search_mode(question) == SearchMode.NEWS

@pytest.mark.parametrize('question', GENERAL_REQUESTS)
def test_explanations_and_historical_sport_keep_general_search(question):
    assert KnowledgeService.detect_search_mode(question) == SearchMode.GENERAL


def source():
    # Synthetic facts, not a claim about a real sporting result.
    return SearchResult('Finale WNBA : compte rendu', 'https://sport.example/wnba/finale',
                        'Dans cet exemple fictif, les Comètes gagnent le match trois 81 à 77.',
                        published_date='2026-10-22')

class Brain:
    def __init__(self, response='Les Comètes gagnent 81 à 77.', error=None):
        self.response=response;self.error=error;self.calls=[]
    def answer_from_sources(self, question, results, **kwargs):
        self.calls.append((question,results,kwargs))
        if self.error:raise self.error
        return self.response

class SequenceProvider:
    def __init__(self, outcomes):self.outcomes=iter(outcomes);self.calls=[]
    def search(self,query,mode=SearchMode.GENERAL):
        self.calls.append((query,mode))
        outcome=next(self.outcomes,[])
        if isinstance(outcome,Exception):raise outcome
        return outcome

@pytest.mark.parametrize('question', [NEWS_REQUESTS[0], 'Donne-moi des informations sur les volcans', 'WNBA Finals 2019'])
@pytest.mark.parametrize('first', [[], SearXNGError('timeout'), [SearchResult('','','')]])
def test_empty_failed_or_unusable_first_search_recovers(question,first):
    provider=SequenceProvider([first,[source()]])
    brain=Brain();service=KnowledgeService(brain,provider)
    answer=service.answer(question)
    assert answer.external_knowledge_retrieved
    assert '81' in answer.message and answer.sources[0].url==source().url
    assert len(brain.calls)==1 and brain.calls[0][0]==question
    assert 1<len(provider.calls)<=3 and len(set(provider.calls))==len(provider.calls)

@pytest.mark.parametrize('outcome', [[],SearXNGError('down')])
def test_retries_are_bounded_and_do_not_call_the_model_without_evidence(outcome):
    provider=SequenceProvider([outcome]*10);brain=Brain()
    answer=KnowledgeService(brain,provider).answer(NEWS_REQUESTS[0])
    assert 1<len(provider.calls)<=3 and not brain.calls
    assert not answer.external_knowledge_retrieved and not answer.sources
    assert 'fiables' not in answer.message  # transport/empty results are not a reliability judgement
    assert answer.failure_reason==('unavailable' if isinstance(outcome,Exception) else 'no_results')

@pytest.mark.parametrize('response', ['', '   ', None])
def test_empty_synthesis_is_an_explicit_failure_with_sources_preserved(response):
    answer=KnowledgeService(Brain(response),SequenceProvider([[source()]])).answer('WNBA')
    assert answer.failure_reason=='synthesis_failed' and answer.sources
    assert answer.message.strip() and answer.external_knowledge_retrieved


def test_success_stops_retries_and_uses_only_retrieved_sources():
    brain=Brain();provider=SequenceProvider([[source()],[SearchResult('invented','https://wrong.example')]])
    answer=KnowledgeService(brain,provider).answer('WNBA')
    assert len(provider.calls)==1 and len(brain.calls)==1
    assert [r.url for r in answer.sources]==[source().url]


def test_provider_outage_does_not_leak_raw_errors():
    answer=KnowledgeService(Brain(),SequenceProvider([SearXNGError('SECRET_PROVIDER_TOKEN')]*3)).answer('WNBA')
    assert 'SECRET_PROVIDER_TOKEN' not in answer.message and not answer.external_knowledge_retrieved

@pytest.mark.parametrize('error', [TimeoutError(),urllib.error.URLError('down'),urllib.error.HTTPError('https://search.example',429,'limit',{},None)])
def test_general_transport_failure_is_not_silently_reported_as_zero_results(error):
    def fail(*args,**kwargs):raise error
    with pytest.raises(SearXNGError):KeylessWebProvider(opener=fail).search('WNBA')

@pytest.mark.parametrize('body', [b'<html>captcha challenge</html>',b'<html><title>Access denied</title></html>',b'not a result page'])
def test_unrecognized_search_markup_is_not_a_valid_empty_search(body):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return body
    with pytest.raises(SearXNGError):KeylessWebProvider(opener=lambda *a,**k:Response()).search('WNBA')


def test_synthesis_failure_is_not_announced_as_a_completed_answer():
    answer=KnowledgeService(Brain(error=RuntimeError('SECRET')),SequenceProvider([[source()]])).answer('WNBA')
    result=KnowledgeCapability(SimpleNamespace(answer=lambda question:answer)).answer('WNBA')
    text=web_announcement_for(result)
    assert result.data['search_status']=='synthesis_failed'
    assert 'La recherche web est terminee' not in text and 'SECRET' not in text

@pytest.mark.parametrize('first', [[],SearXNGError('down')])
def test_registered_background_search_delivers_recovered_answer_to_user(first):
    from jarvis.live.registry import create_live_registry
    async def scenario():
        capability=KnowledgeCapability(KnowledgeService(Brain(),SequenceProvider([first,[source()]])))
        registry=create_live_registry(knowledge_capability=capability);spoken=[]
        async def announce(message):spoken.append(message)
        registry.set_task_notifier(announce)
        try:
            tools={tool.info.name:tool for tool in registry.livekit_tools()}
            ack=await tools['search_the_web'](NEWS_REQUESTS[0])
            await registry._web_task
            assert ack['search_started'] and len(spoken)==1
            assert '81' in spoken[0] and 'insuffisantes' not in spoken[0]
        finally:await registry.aclose()
    asyncio.run(scenario())


def test_unexpected_service_errors_never_expose_provider_credentials():
    def fail(question):raise RuntimeError('PRIVATE_PROVIDER_TOKEN')
    result=KnowledgeCapability(SimpleNamespace(answer=fail)).answer('WNBA')
    assert not result.ok and result.error_code=='system_error'
    assert 'PRIVATE_PROVIDER_TOKEN' not in result.message

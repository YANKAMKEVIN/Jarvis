"""Provider payloads must preserve facts or report an unavailable source."""
import json
import pytest
from jarvis.knowledge.keyless import KeylessWebProvider
from jarvis.knowledge.searxng import SearXNGProvider,SearXNGError
from jarvis.knowledge.models import SearchMode

class Response:
    def __init__(self,body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def getcode(self):return 200
    def read(self,*a):return self.body

@pytest.mark.parametrize('payload',[None,[],True,42,'string',{'results':None},{'results':'not a list'},{'error':'engine failed'}])
def test_malformed_searx_payload_is_a_provider_failure(payload):
    provider=SearXNGProvider(urlopen=lambda *a,**k:Response(json.dumps(payload).encode()))
    with pytest.raises(SearXNGError):provider.search('WNBA')

@pytest.mark.parametrize('tag',['span','b','strong','em'])
def test_nested_markup_preserves_the_complete_evidence(tag):
    html=f'<a class="result__a" href="https://sport.example/wnba">Finale WNBA</a><div class="result__snippet">Les Comètes <{tag}>remportent</{tag}> le match 81 à 77.</div>'
    provider=KeylessWebProvider(opener=lambda *a,**k:Response(html.encode()))
    rows=provider.search('WNBA')
    assert len(rows)==1 and '81 à 77' in rows[0].snippet
    assert 'Comètes remportent le match' in rows[0].snippet

@pytest.mark.parametrize('body',[b'<html>Access denied</html>',b'<error>Rate limited</error>',b'<rss>truncated'])
def test_news_error_pages_are_not_mistaken_for_no_articles(body):
    provider=KeylessWebProvider(opener=lambda *a,**k:Response(body))
    with pytest.raises(SearXNGError):provider.search('WNBA',SearchMode.NEWS)

@pytest.mark.parametrize('body',[b'<html><div class="no-results">No results found</div></html>',b'<rss><channel/></rss>'])
def test_genuine_empty_search_is_distinct_from_a_broken_provider(body):
    provider=KeylessWebProvider(opener=lambda *a,**k:Response(body))
    mode=SearchMode.NEWS if body.startswith(b'<rss>') else SearchMode.GENERAL
    assert provider.search('unknown very specific request',mode)==[]

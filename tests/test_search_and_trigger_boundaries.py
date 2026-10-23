"""Boundary cases selected from the branch-coverage report."""
import json
from types import SimpleNamespace
import pytest
from jarvis.desktop.experience_storage import load_triggers,save_trigger
from jarvis.knowledge.keyless import KeylessWebProvider,FallbackProvider
from jarvis.knowledge.searxng import SearXNGError

class Settings:
    def __init__(self,value='[]'):self.values={'experience/triggers':value}
    def value(self,key,default=None):return self.values.get(key,default)
    def setValue(self,key,value):self.values[key]=value

@pytest.mark.parametrize('raw',['{','null','false','42','"text"',None])
def test_invalid_settings_payload_loads_as_an_empty_list(raw):
    assert load_triggers(Settings(raw))==[]

@pytest.mark.parametrize('routine,kind,value',[
    ('','time','09:00'),('x'*81,'time','09:00'),('Valid','time',''),
    ('Valid','time','24:00'),('Valid','time','12:60'),('Valid','time','tomorrow'),
    ('Valid','unknown','Safari'),('Valid','application','x'*181),
])
def test_invalid_trigger_never_changes_saved_preferences(routine,kind,value):
    settings=Settings();before=dict(settings.values)
    with pytest.raises(ValueError):save_trigger(settings,routine,kind,value)
    assert settings.values==before

@pytest.mark.parametrize('kind,value',[('time','00:00'),('time','23:59'),('application','com.apple.Safari')])
def test_valid_trigger_round_trip_and_hard_limit(kind,value):
    settings=Settings()
    first=save_trigger(settings,'Review',kind,value)
    assert load_triggers(settings)==[first]
    for _ in range(49):save_trigger(settings,'Review',kind,value)
    assert len({row['id'] for row in load_triggers(settings)})==50
    before=dict(settings.values)
    with pytest.raises(ValueError):save_trigger(settings,'Overflow',kind,value)
    assert settings.values==before

@pytest.mark.parametrize('url',['','file:///etc/passwd','javascript:alert(1)','ftp://server/file','not a URL'])
def test_page_reader_rejects_non_web_inputs_without_network(url):
    def forbidden(*a,**k):pytest.fail('Invalid URL reached the network')
    with pytest.raises(SearXNGError):KeylessWebProvider(opener=forbidden).fetch_text(url)


def test_page_reader_bounds_text_and_preserves_accents():
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,*args):return ('<p>Équipe gagnante</p> '+'x'*1000).encode()
    text=KeylessWebProvider(opener=lambda *a,**k:Response()).fetch_text('https://news.example',max_chars=200)
    assert text.startswith('Équipe gagnante') and len(text)==200


def test_unexpected_fallback_failure_becomes_provider_failure():
    def down(*a,**k):raise RuntimeError('INTERNAL_PROVIDER_ERROR')
    provider=FallbackProvider(SimpleNamespace(search=down),SimpleNamespace(search=down))
    with pytest.raises(SearXNGError) as caught:provider.search('WNBA')
    assert 'INTERNAL_PROVIDER_ERROR' not in str(caught.value)

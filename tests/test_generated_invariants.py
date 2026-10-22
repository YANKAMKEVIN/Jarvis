"""Generated user data and action sequences, checked against independent state."""
import tempfile
from pathlib import Path
from types import SimpleNamespace
from datetime import date
from hypothesis import given, settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, invariant, initialize
import pytest
from jarvis.live.confirmation import PendingActionStore
from jarvis.knowledge.models import SearchMode, SearchResult
from jarvis.knowledge.service import KnowledgeService
from jarvis.capabilities.notes import NotesCapability
from jarvis.desktop.experience_storage import load_triggers

words=st.text(alphabet='abcdefghijklmnopqrstuvwxyz éàèç0123456789',min_size=1,max_size=50).filter(lambda s:bool(s.strip()))

@given(st.lists(st.integers(min_value=0,max_value=30),max_size=80))
@settings(max_examples=100,derandomize=True,deadline=None)
def test_source_selection_deduplicates_without_inventing_urls(ids):
    rows=[SearchResult(str(i),f'https://news.example/article/{i}','Some evidence') for i in ids]
    selected=KnowledgeService(None)._select_results(rows)
    urls=[row.url for row in selected]
    assert len(urls)<=5 and len(urls)==len(set(urls))
    assert urls==list(dict.fromkeys(row.url for row in rows))[:5]

@given(words,words)
@settings(max_examples=50,derandomize=True,deadline=None)
def test_notes_append_preserves_original_and_survives_reopen(original,addition):
    with tempfile.TemporaryDirectory() as root:
        cap=NotesCapability(root)
        saved=cap.save_note(original,'Note de test')
        assert saved.ok
        path=Path(saved.data['path']);before=path.read_bytes()
        assert cap.append_note(path.name,addition).ok
        assert path.read_bytes().startswith(before)
        read=NotesCapability(root).read_note(path.name)
        assert original.strip() in read.data['text'] and addition.strip() in read.data['text']
        assert len(list(Path(root).iterdir()))==1

json_scalars=st.one_of(st.none(),st.booleans(),st.integers(),st.text(max_size=30))
json_values=st.recursive(json_scalars,lambda child:st.one_of(st.lists(child,max_size=5),st.dictionaries(st.text(max_size=12),child,max_size=5)),max_leaves=15)

@given(json_values)
@settings(max_examples=100,derandomize=True,deadline=None)
def test_corrupt_trigger_settings_never_crash_or_enable_a_routine(value):
    import json
    settings_stub=SimpleNamespace(value=lambda *a:json.dumps(value))
    rows=load_triggers(settings_stub)
    assert isinstance(rows,list) and len(rows)<=50
    for row in rows:
        assert row['kind'] in {'time','application'}
        assert isinstance(row['routine'],str)

@pytest.mark.parametrize('kind',[[],{},1,None,True])
def test_corrupt_trigger_kind_is_ignored(kind):
    import json
    value=[{'id':'row','routine':'Ranger','kind':kind,'value':'09:00','enabled':True}]
    assert load_triggers(SimpleNamespace(value=lambda *a:json.dumps(value)))==[]

@pytest.mark.parametrize('url',['javascript:alert(1)','file:///etc/passwd','data:text/plain,hello','http://','https://[broken','//news.example/article','relative/article',''])
def test_unusable_source_urls_are_not_evidence(url):
    assert KnowledgeService(None)._select_results([SearchResult('Title',url,'Evidence')])==[]

class ConfirmationSequence(RuleBasedStateMachine):
    @initialize()
    def setup(self):
        self.now=0.;self.serial=0;self.pending={};self.seen=set()
        def token():self.serial+=1;return f'token-{self.serial}'
        self.store=PendingActionStore(clock=lambda:self.now,token_factory=token,ttl_seconds=10,max_pending=4)
    def prune(self):
        self.pending={token:created for token,created in self.pending.items() if self.now-created<=10}
    @rule()
    def register(self):
        self.prune();token=self.store.register('send',lambda:pytest.fail('No action executes during preparation'))
        self.pending[token]=self.now
        if len(self.pending)>4:self.pending.pop(next(iter(self.pending)))
        assert token not in self.seen;self.seen.add(token)
    @rule(seconds=st.integers(min_value=0,max_value=20))
    def advance(self,seconds):self.now+=seconds;self.prune()
    @rule(index=st.integers(min_value=0,max_value=20),cancel=st.booleans())
    def consume(self,index,cancel):
        self.prune();token=f'token-{index}'
        expected=token in self.pending
        result=(self.store.cancel if cancel else self.store.confirm)(token)
        assert (result is not None)==expected
        self.pending.pop(token,None)
        assert self.store.confirm(token) is None
    @invariant()
    def pending_status_matches_user_visible_state(self):
        self.prune();assert self.store.has_pending()==bool(self.pending)

TestConfirmationSequences=ConfirmationSequence.TestCase
TestConfirmationSequences.settings=settings(max_examples=40,stateful_step_count=35,derandomize=True,deadline=None)

"""Cross-tool safety contracts: observable side effects, consent and file identity."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from jarvis.live.registry import create_live_registry, SAFE_MODE_ALLOWED
from jarvis.desktop.experience_core import UndoLedger
from jarvis.capabilities.document import DocumentCapability
from jarvis.document_consent import REMOTE_DOCUMENT_PERMISSION
from jarvis.tools.filesystem import FileSystemTools, PathResolver

# Every mutating tool is exercised through both public execution surfaces. No
# underlying capability may be reached; bombs keep these tests hardware-free.
_probe=create_live_registry(memory_capability=SimpleNamespace(log_action=lambda *a,**k:None))
LIVE_BLOCKED=sorted(t.info.name for t in _probe.livekit_tools() if t.info.name not in SAFE_MODE_ALLOWED)
PLANNER_BLOCKED=sorted(t.info.name for t in _probe.planner_tools if t.info.name not in SAFE_MODE_ALLOWED)
CASES=[('voice',name) for name in LIVE_BLOCKED]+[('planner',name) for name in PLANNER_BLOCKED]
del _probe

@pytest.mark.parametrize('surface,name',CASES,ids=lambda item:str(item))
def test_every_mutating_tool_refuses_before_reaching_its_body(surface,name):
    async def run():
        registry=create_live_registry(memory_capability=SimpleNamespace(log_action=lambda *a,**k:None))
        voice_tools=registry.livekit_tools()
        tools=voice_tools if surface=='voice' else registry.planner_tools
        registry.read_only_mode=True
        class ForbiddenCapability:
            def __getattr__(self, attribute):
                raise AssertionError(f'Blocked tool reached capability: {attribute}')
        for attribute in ('audio','apps','media','system','windows','files','clipboard','keyboard','mouse','ui_accessibility','interaction','browser','screenshot','vision','messaging','calendar','mail','claude_sessions','text_workshop','shortcuts','webread','document'):
            setattr(registry,attribute,ForbiddenCapability())
        # No arguments is deliberate: refusal must happen before validation or
        # capability invocation, even for a malformed model tool request.
        tool=next(t for t in tools if t.info.name==name)
        try:
            result=await tool()
            assert result['ok'] is False and result['error_code']=='read_only_mode'
            assert not result.get('state_confirmed')
        finally:await registry.aclose()
    asyncio.run(run())

@pytest.mark.parametrize('permission',[None,False,True])
@pytest.mark.parametrize('env',['0','1'])
@pytest.mark.parametrize('endpoint',['http://localhost:11434/api/chat','http://127.0.0.1:11434/api/chat','https://model.example/chat','https://localhost.evil.example/chat'])
@pytest.mark.parametrize('operation',['ask','extract','compare'])
def test_document_text_never_leaves_without_effective_consent(tmp_path,monkeypatch,permission,env,endpoint,operation):
    monkeypatch.setenv('JARVIS_DOCUMENT_ALLOW_REMOTE',env)
    model=SimpleNamespace(base_url=endpoint,complete=Mock(return_value=SimpleNamespace(text='{}',tool_calls=[])))
    left=tmp_path/'left.txt';left.write_text('PRIVATE_DOCUMENT_MARKER')
    right=tmp_path/'right.txt';right.write_text('PRIVATE_SECOND_MARKER')
    capability=DocumentCapability(FileSystemTools(resolver=PathResolver(home=tmp_path)),model)
    token=REMOTE_DOCUMENT_PERMISSION.set(permission)
    try:
        if operation=='ask':result=capability.ask(str(left),'Résumé ?')
        elif operation=='extract':result=capability.extract_actions(str(left))
        else:result=capability.compare(str(left),str(right))
    finally:REMOTE_DOCUMENT_PERMISSION.reset(token)
    local=endpoint.startswith(('http://localhost:','http://127.0.0.1:'))
    allowed=local or permission is True or (permission is None and env=='1')
    assert bool(model.complete.call_count)==allowed
    if not allowed:assert result.error_code=='remote_model_blocked'
    assert left.read_text()=='PRIVATE_DOCUMENT_MARKER' and right.read_text()=='PRIVATE_SECOND_MARKER'


def test_concurrent_document_consents_do_not_leak_between_requests(tmp_path,monkeypatch):
    monkeypatch.setenv('JARVIS_DOCUMENT_ALLOW_REMOTE','1')
    path=tmp_path/'private.txt';path.write_text('PRIVATE')
    async def run():
        async def request(allowed):
            calls=[]
            model=SimpleNamespace(base_url='https://model.example',complete=lambda *a:(calls.append(True) or SimpleNamespace(text='Answer',tool_calls=[])))
            cap=DocumentCapability(FileSystemTools(resolver=PathResolver(home=tmp_path)),model)
            token=REMOTE_DOCUMENT_PERMISSION.set(allowed)
            try:
                await asyncio.sleep(0)
                result=await asyncio.to_thread(cap.ask,str(path),'Question')
                return result.ok,bool(calls)
            finally:REMOTE_DOCUMENT_PERMISSION.reset(token)
        outcomes=await asyncio.gather(*(request(bool(i%2)) for i in range(20)))
        assert outcomes==[(bool(i%2),bool(i%2)) for i in range(20)]
        assert REMOTE_DOCUMENT_PERMISSION.get() is None
    asyncio.run(run())

@pytest.mark.parametrize('change',['contents','replacement','missing','symlink','occupied_origin','origin_symlink'])
def test_undo_never_overwrites_or_reverts_a_different_file(tmp_path,change):
    old=tmp_path/'old.txt';new=tmp_path/'new.txt';new.write_text('original')
    ledger=UndoLedger();ledger.record('move_file',{'ok':True,'state_confirmed':True,'previous_path':str(old),'path':str(new)})
    ticket=next(iter(ledger.tickets))
    if change=='contents':new.write_text('changed content')
    elif change=='replacement':new.unlink();new.write_text('replacement')
    elif change=='missing':new.unlink()
    elif change=='symlink':new.unlink();new.symlink_to(tmp_path/'other')
    elif change=='occupied_origin':old.write_text('do not overwrite')
    else:old.symlink_to(tmp_path/'missing')
    before={p.name:(p.read_bytes() if p.is_file() and not p.is_symlink() else None) for p in tmp_path.iterdir()}
    with pytest.raises(ValueError):ledger.validate(ticket)
    after={p.name:(p.read_bytes() if p.is_file() and not p.is_symlink() else None) for p in tmp_path.iterdir()}
    assert after==before

from pathlib import Path
import zipfile
import pytest
from jarvis.tools.filesystem import FileSystemTools,PathResolver,FileSystemError


def test_docx_runs_and_paragraphs_are_extracted_without_opening_office(tmp_path):
    path=tmp_path/'report.docx'
    xml='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hel</w:t></w:r><w:r><w:t>lo</w:t></w:r></w:p><w:p><w:r><w:t>World</w:t></w:r></w:p></w:body></w:document>'
    with zipfile.ZipFile(path,'w') as archive:archive.writestr('word/document.xml',xml)
    tools=FileSystemTools(resolver=PathResolver(home=tmp_path))
    result=tools.read_text(path)
    assert result['text']=='Hello\nWorld' and result['char_count']==11


def test_docx_external_entities_are_never_loaded(tmp_path):
    path=tmp_path/'bad.docx'
    with zipfile.ZipFile(path,'w') as archive:archive.writestr('word/document.xml','<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>')
    with pytest.raises(FileSystemError):FileSystemTools._read_docx_text(path)


def test_text_reads_are_bounded_before_decoding(tmp_path,monkeypatch):
    path=tmp_path/'large.txt';path.write_text('a'*100000)
    tools=FileSystemTools(resolver=PathResolver(home=tmp_path))
    monkeypatch.setattr(Path,'read_bytes',lambda self: (_ for _ in ()).throw(AssertionError('unbounded read')))
    result=tools.read_text(path,max_chars=200)
    assert len(result['text'])==200 and result['truncated']


def test_remote_document_consent_is_scoped_and_can_override_environment(tmp_path,monkeypatch):
    from jarvis.document_consent import REMOTE_DOCUMENT_PERMISSION
    from jarvis.capabilities.document import DocumentCapability
    from types import SimpleNamespace as NS
    class Remote:
        base_url='https://example.com/model'
        def complete(self,messages,tools):return NS(text='Answer',tool_calls=[])
    path=tmp_path/'private.txt';path.write_text('Only with consent')
    capability=DocumentCapability(FileSystemTools(resolver=PathResolver(home=tmp_path)),Remote())
    monkeypatch.delenv('JARVIS_DOCUMENT_ALLOW_REMOTE',raising=False)
    blocked=capability.ask(str(path),'Question')
    assert not blocked.ok
    token=REMOTE_DOCUMENT_PERMISSION.set(True)
    try:assert capability.ask(str(path),'Question').ok
    finally:REMOTE_DOCUMENT_PERMISSION.reset(token)
    monkeypatch.setenv('JARVIS_DOCUMENT_ALLOW_REMOTE','1')
    token=REMOTE_DOCUMENT_PERMISSION.set(False)
    try:assert capability.ask(str(path),'Question').error_code=='remote_model_blocked'
    finally:REMOTE_DOCUMENT_PERMISSION.reset(token)

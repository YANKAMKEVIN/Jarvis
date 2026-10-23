"""Document completeness and archive leakage: synthetic files/data only."""
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import zipfile

from jarvis.tools.filesystem import FileSystemTools,PathResolver
from jarvis.capabilities.document import DocumentCapability
from jarvis.desktop.result_history import archive_receipt


def test_page_limit_is_reported_as_incomplete_even_for_short_pdf_pages(tmp_path):
    path=tmp_path/'partial.pdf';path.write_bytes(b'fixture')
    class Page:
        def extract_text(self):return 'QA'
    with patch('pypdf.PdfReader',return_value=NS(pages=[Page() for _ in range(51)])):
        result=FileSystemTools(resolver=PathResolver(home=tmp_path)).read_text(path)
    assert result['truncated'] is True


def test_pdf_stops_extracting_pages_once_text_budget_is_exceeded(tmp_path):
    path=tmp_path/'bounded.pdf';path.write_bytes(b'fixture')
    calls=[]
    class Page:
        def extract_text(self):calls.append(1);return 'QA '*200
    with patch('pypdf.PdfReader',return_value=NS(pages=[Page() for _ in range(50)])):
        result=FileSystemTools(resolver=PathResolver(home=tmp_path)).read_text(path,max_chars=200)
    assert result['truncated'] and len(result['text'])==200
    assert len(calls)==1


def test_real_pdf_page_limit_metadata_survives_document_analysis(tmp_path):
    from pypdf import PdfWriter
    path=tmp_path/'real.pdf'
    writer=PdfWriter()
    for _ in range(51):writer.add_blank_page(width=72,height=72)
    with path.open('wb') as stream:writer.write(stream)
    model=NS(complete=lambda *args:NS(text='Le document ne fournit aucun texte.',tool_calls=[]))
    result=DocumentCapability(FileSystemTools(resolver=PathResolver(home=tmp_path)),model).ask(str(path),'Que contient-il ?')
    assert result.ok and result.data['truncated'] is True


def test_secret_in_parent_directory_is_not_archived(tmp_path):
    sensitive=str(tmp_path/'password:synthetic-credential'/'report.txt')
    row=archive_receipt('read_file','QA',{'ok':True,'path':sensitive,'message':'Result'},{'label':'Document'})
    assert row['paths']==[]
    assert 'synthetic-credential' not in str(row)


def test_regular_path_is_still_available_in_archive(tmp_path):
    normal=str(tmp_path/'report.txt')
    row=archive_receipt('read_file','QA',{'ok':True,'path':normal,'message':'Result'},{'label':'Document'})
    assert row['paths']==[normal]

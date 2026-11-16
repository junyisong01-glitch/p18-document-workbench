"""Runtime isolation, fallback and WAL checks with synthetic data."""
from pathlib import Path
import sys,sqlite3
import pytest
from app import main,parser


def test_only_docx_routes_to_optional_worker(monkeypatch):
    monkeypatch.setenv('P18_PARSER','docling');monkeypatch.setenv('P18_DOCX_PYTHON',sys.executable)
    assert main.parser_python('.docx')==sys.executable
    monkeypatch.setenv('P18_DOCX_PYTHON','/missing/worker')
    for ext in ['.pdf','.xlsx','.doc']:assert main.parser_python(ext)==sys.executable
    with pytest.raises(ValueError):main.parser_python('.docx')
    monkeypatch.setenv('P18_PARSER','legacy');assert main.parser_python('.docx')==sys.executable


def test_unsupported_docling_uses_explicit_legacy_fallback(tmp_path,monkeypatch):
    from docx import Document
    from app import docling_parser
    d=Document();d.add_paragraph('    exact_code()');p=tmp_path/'code.docx';d.save(p)
    monkeypatch.setenv('P18_PARSER','docling');monkeypatch.setenv('P18_DOCLING_FALLBACK','legacy');monkeypatch.setattr(docling_parser,'available',lambda:True)
    r=parser.parse_word_selected(p)
    assert r['blocks'][0]['text']=='    exact_code()' and 'legacy-fallback'in r['parser_version']
    assert r['issues'][-1]['kind']=='parser_fallback'


def test_missing_docling_text_cannot_silently_pass(tmp_path,monkeypatch):
    from docx import Document
    from app import docling_parser
    d=Document();d.add_paragraph('KEY NUMBER 781');p=tmp_path/'x.docx';d.save(p)
    monkeypatch.setenv('P18_PARSER','docling');monkeypatch.setenv('P18_DOCLING_FALLBACK','legacy');monkeypatch.setattr(docling_parser,'available',lambda:True);monkeypatch.setattr(docling_parser,'extract_word',lambda path:{'blocks':[{'text':'incomplete'}]})
    r=parser.parse_word_selected(p);assert r['blocks'][0]['text']=='KEY NUMBER 781' and r['issues'][-1]['kind']=='parser_fallback'


def test_wal_committed_reader_and_disable_rollback_preserve_rows(tmp_path):
    path=tmp_path/'synthetic.sqlite3';writer=sqlite3.connect(path);reader=sqlite3.connect(path,timeout=.1)
    writer.execute('create table entries(v)');writer.execute('insert into entries values(1)');writer.commit();assert writer.execute('pragma journal_mode=WAL').fetchone()[0]=='wal'
    writer.execute('begin immediate');writer.execute('update entries set v=2');assert reader.execute('select v from entries').fetchone()[0]==1
    writer.commit();assert reader.execute('select v from entries').fetchone()[0]==2;reader.close();writer.execute('pragma wal_checkpoint(TRUNCATE)');assert writer.execute('pragma journal_mode=DELETE').fetchone()[0]=='delete';assert writer.execute('select v from entries').fetchone()[0]==2;writer.close()

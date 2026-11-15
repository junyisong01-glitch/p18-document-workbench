"""Remaining integrations: synthetic data, no models or outside services by default."""
from pathlib import Path
import sqlite3,json,threading
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from app import main, library_api, library_store
from app.library_policy import LibraryMetadata
from test_library_api import setup


def test_batch_visibility_matches_scalar_and_rechecks_revocation(setup):
    client,headers,docs=setup
    with main.connect() as conn:
        for doc in docs:
            doc.update(name=doc['id']+'.pdf',revision=1)
            conn.execute('UPDATE documents SET body=? WHERE id=?',(json.dumps(doc),doc['id']))
    for kind in ['rd','hr','admin']:
        response=client.get('/api/library/documents',headers=headers[kind]);full=response.json()
        assert {d['id'] for d in full}=={'rd':{'public','archive'},'hr':{'public','secret','archive'},'admin':{'public','archive','unclassified'}}[kind]
        assert int(response.headers['X-Total-Count'])==len(full)
        page=client.get('/api/library/documents?limit=1&offset=1',headers=headers[kind]);assert page.json()==full[1:2]and int(page.headers['X-Total-Count'])==len(full)
    for path in ['?limit=0','?limit=201','?offset=-1']:assert client.get('/api/library/documents'+path,headers=headers['rd']).status_code==422
    with main.connect()as c:c.execute('UPDATE library_sessions SET expires=0')
    assert client.get('/api/library/documents?limit=1',headers=headers['rd']).status_code==401


def test_batch_overlay_cannot_replace_document_policy():
    calls=[];store=SimpleNamespace(authorize_document=lambda doc,user,**k:calls.append(doc['id'])or doc['id']=='a')
    token=library_api.principal.set({'identity':'synthetic'})
    try:assert library_api.visible_ids(store,[{'id':'a'},{'id':'b'}])=={'a'}and calls==['a','b']
    finally:library_api.principal.reset(token)


def test_strict_index_state_kept(setup):
    c,h,_=setup
    assert all(d['status']!='可检索'for d in c.get('/api/library/documents',headers=h['rd']).json())


@pytest.mark.parametrize('enabled,expected',[('0','delete'),('1','wal')])
def test_wal_only_when_explicit_in_empty_test_database(tmp_path,monkeypatch,enabled,expected):
    monkeypatch.setattr(main,'DATA',tmp_path);monkeypatch.setattr(main,'DB',tmp_path/'empty.sqlite3');monkeypatch.setenv('P18_SQLITE_WAL',enabled);main.initialize()
    with main.connect()as c:assert c.execute('PRAGMA journal_mode').fetchone()[0]==expected


def test_docling_never_auto_enabled_by_installation(monkeypatch):
    from app import parser,docling_parser
    monkeypatch.delenv('P18_PARSER',raising=False);monkeypatch.setattr(docling_parser,'available',lambda:True);monkeypatch.setattr(parser,'parse_word',lambda p:{'backend':'legacy'})
    assert parser.parse_word_selected('fixture.docx')=={'backend':'legacy'}
    monkeypatch.setenv('P18_PARSER','docling');monkeypatch.setattr(docling_parser,'available',lambda:False)
    with pytest.raises(ValueError,match='未安装'):parser.parse_word_selected('fixture.docx')
    monkeypatch.setenv('P18_PARSER','wrong')
    with pytest.raises(ValueError):parser.parse_word_selected('fixture.docx')


def test_pdf_stays_legacy_when_docling_flag_set(tmp_path,monkeypatch):
    from app import parser
    import pymupdf as fitz
    monkeypatch.setenv('P18_PARSER','docling');d=fitz.open();d.new_page().insert_text((40,60),'Synthetic PDF content');d.save(tmp_path/'original.pdf');d.close()
    result=parser.process(tmp_path,'.pdf');assert result['blocks'][0]['id']=='page-1'and result['parser_version']=='word-structure-v2'


def test_doctor_refuses_foreign_listener(tmp_path,monkeypatch):
    import importlib.util
    spec=importlib.util.spec_from_file_location('doctor',Path(__file__).parents[1]/'scripts/doctor.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setattr(m,'ROOT',tmp_path);(tmp_path/'config').mkdir();(tmp_path/'config/demo-v1.json').write_text(json.dumps({'model_cache':'cache','embedding_revision':'a'*40,'converter':''}));data=tmp_path/'runtime/demo-v1-experience';data.mkdir(parents=True);(data/'service.json').write_text(json.dumps({'pid':123}))
    monkeypatch.setattr(m.subprocess,'run',lambda args,**k:SimpleNamespace(stdout='456\n'if '-t'in args else'n/foreign'))
    monkeypatch.setattr(m.socket,'socket',lambda:SimpleNamespace(connect_ex=lambda address:0,close=lambda:None))
    assert m.main()==1;assert next(r for r in m.RESULTS if r[0]=='8896 端口')[1]is False


def test_technical_index_brackets_do_not_weaken_citation_protocol():
    from app.rag import RagService,RagError
    evidence=[{'id':'S1','text':'arr[0] 和 list[key] 是虚构技术示例'}]
    raw=lambda text:json.dumps({'status':'answered','answer':text,'citations':['S1']})
    assert RagService.validate_answer(raw('读取 arr[0] 和 list[key]。[S1]'),evidence)[0]=='answered'
    for answer in ['读取 unknown[XX]。[S1]','读取 arr[S99]。[S1]','无依据[XX]。[S1]','读取[SXX]。[S1]','读取 https://bad.example。[S1]']:
        with pytest.raises(RagError):RagService.validate_answer(raw(answer),evidence)


def test_list_rechecks_session_when_revoked_during_record_build(setup,monkeypatch):
    c,h,docs=setup;original=library_api.library_record;done=[]
    def revoke_midway(store,doc):
        result=original(store,doc)
        if not done:
            with store.connect()as conn:conn.execute('UPDATE library_sessions SET expires=0')
            done.append(True)
        return result
    monkeypatch.setattr(library_api,'library_record',revoke_midway)
    response=c.get('/api/library/documents',headers=h['rd']);assert response.status_code==200 and response.json()==[] and response.headers['X-Total-Count']=='0'


def test_legacy_doc_conversion_does_not_switch_backend(tmp_path,monkeypatch):
    from app import parser
    from docx import Document
    d=Document();d.add_paragraph('虚构转换正文');converted=tmp_path/'converted.docx';d.save(converted);(tmp_path/'original.doc').write_bytes(b'synthetic binary stub')
    monkeypatch.setenv('P18_PARSER','docling');monkeypatch.setattr(parser,'validate',lambda *a:None)
    def convert(source,folder,kind):
        if kind=='docx':return converted
        raise ValueError('synthetic preview unavailable')
    monkeypatch.setattr(parser,'convert',convert)
    result=parser.process(tmp_path,'.doc');assert result['parser_version']=='word-structure-v2'and result['blocks'][0]['text']=='虚构转换正文'

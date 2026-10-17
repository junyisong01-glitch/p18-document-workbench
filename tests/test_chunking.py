import copy
import io
import json
import re
import sqlite3
import threading
import time
from unittest.mock import patch

import pytest
from docx import Document

from app import main
from app.admission import sync_admission
from app.chunking import configuration, digest, prepare
from app.parser import convert, parse_pdf, parse_word, soffice_path
from test_workbench import client, upload, wait, pdf_bytes, HEADERS


def sample(blocks, ext='.docx'):
    doc={'id':'3dd7d9cc-ccce-4e9c-a1e2-17e9ec61652a', 'revision':1,'state':'ready',
         'quality':'clear', 'ext':ext,'characters':100, 'result':{'blocks':blocks,'issues':[]}}
    sync_admission(doc)
    return doc


def paragraph(number,text,section='正文',**extra):
    return {'id':f'paragraph-{number}','kind':'paragraph','label':f'{section} · 段落 {number}',
            'section':section,'text':text,'tables':[],**extra}


def compact(text):return re.sub(r'\s+','',text)


def wait_chunks(client,identifier,status='complete'):
    for _ in range(400):
        result=client.get(f'/api/documents/{identifier}/chunks').json()
        if result['status'] not in {'not_started','queued','processing'}:
            assert result['status']==status,result
            return result
        time.sleep(.02)
    raise AssertionError('切分任务超时')


def test_order_headings_source_coverage_and_raw_unchanged():
    blocks=[paragraph(1,'第一章 预约',section='第一章 预约',heading_level=1),
            paragraph(2,'预约说明。'*130,section='第一章 预约'),
            paragraph(3,'第二章 取消',section='第二章 取消',heading_level=1),
            paragraph(4,'取消说明。'*100,section='第二章 取消')]
    doc=sample(blocks);original=copy.deepcopy(doc['result'])
    config={**configuration(),'target_chars':100,'overlap_chars':0}
    normalized,chunks=prepare(doc,config)
    assert doc['result']==original
    assert compact(''.join(c['text'] for c in chunks))==compact(''.join(b['text'] for b in blocks))
    assert [c['order'] for c in chunks]==list(range(1,len(chunks)+1))
    assert all(c['section'] in {'第一章 预约','第二章 取消'} for c in chunks)
    lookup={b['id']:b for b in blocks}
    for c in chunks:
        for src in c['sources']:
            assert src['block_id'] in lookup and 'page' not in src
            assert 0<=src['raw_start']<=src['raw_end']<=len(lookup[src['block_id']]['text'])
    assert normalized['units'] and chunks==prepare(doc,config)[1]


def test_keep_duplicate_technical_clauses_and_no_cross_section_overlap():
    blocks=[paragraph(1,'不得绕过审核。\n\n\n不得绕过审核。','甲'),paragraph(2,'新的技术说明。','乙')]
    normalized,chunks=prepare(sample(blocks),{**configuration(),'target_chars':80,'overlap_chars':30})
    assert ''.join(u['text'] for u in normalized['units']).count('不得绕过审核。')==2
    assert all('不得绕过审核' not in c['text'] for c in chunks if c['section']=='乙')


def test_sentence_overlap_and_unsplittable_long_text():
    doc=sample([paragraph(1,'甲。'*65+'末句。'+'乙。'*65)])
    _,chunks=prepare(doc,{**configuration(),'target_chars':80,'overlap_chars':10})
    assert any(c.get('overlap_chars',0)>0 for c in chunks)
    _,long=prepare(sample([paragraph(1,'A'*170)]),{**configuration(),'target_chars':80,'overlap_chars':0})
    assert ''.join(c['text'] for c in long)=='A'*170


def test_table_row_groups_and_repeated_first_row():
    rows=[['参数','类型','必填','说明']]+[[f'p{i}','string','是',f'编号{i}说明'*10] for i in range(20)]
    raw='\n'.join('\t'.join(row) for row in rows)
    doc=sample([paragraph(1,'表1 参数表','接口'),{'id':'table-1','kind':'table','label':'接口 · 表格 1','text':raw,'tables':[{'rows':rows}]}])
    _,chunks=prepare(doc,{**configuration(),'target_chars':120,'overlap_chars':30})
    table_chunks=[c for c in chunks if c['kind']=='table']
    assert len(table_chunks)>1
    recovered=[]
    for c in table_chunks:
        assert c['table_title']=='表1 参数表'
        assert c['tables'][0]['rows'][0]==rows[0]
        recovered+=c['tables'][0]['rows'][1:]
        assert any(s['block_id']=='table-1' for s in c['sources'])
    assert recovered==rows[1:]
    assert doc['result']['blocks'][1]['text']==raw


def test_code_whitespace_and_steps_remain_structured():
    code='def reserve(device):\n    # 保留缩进\n\n    return {"device": device, "ok": True}\n'
    steps=[f'{i}. 操作{i}：'+'确认参数。'*15 for i in range(1,7)]
    blocks=[paragraph(1,'代码','代码',heading_level=1),paragraph(2,code,'代码'),
            paragraph(3,'操作流程','操作流程',heading_level=1)]+[paragraph(i+4,t,'操作流程') for i,t in enumerate(steps)]
    _,chunks=prepare(sample(blocks),{**configuration(),'target_chars':80,'overlap_chars':20})
    assert next(c for c in chunks if c['kind']=='code')['text']==code
    assert compact(''.join(c['text'] for c in chunks if c['kind']=='steps'))==compact(''.join(steps))
    assert all(any(step in c['text'] for c in chunks) for step in steps)


def test_fenced_code_across_paragraphs_and_doc_conversion_source():
    blocks=[paragraph(i+1,t) for i,t in enumerate(['```python','def f():','', '    return 1','```'])]
    _,chunks=prepare(sample(blocks,ext='.doc'),configuration())
    assert len(chunks)==1 and chunks[0]['text']=='```python\ndef f():\n\n    return 1\n```'
    assert all(s['variant']=='converted' and 'page' not in s for s in chunks[0]['sources'])


def test_pdf_heading_pages_and_table_fallback_no_double_text():
    blocks=[{'id':'page-1','kind':'page','page':1,'label':'第 1 页','text':'一、接口说明\n预约正文。\n预约正文。','tables':[]},
            {'id':'page-2','kind':'page','page':2,'label':'第 2 页','text':'参数\ndevice_id\n说明\n设备编号','tables':[{'rows':[['参数','说明'],['device_id','设备编号']]}]}]
    _,chunks=prepare(sample(blocks,ext='.pdf'),configuration())
    assert chunks[0]['section']=='一、接口说明'
    table=next(c for c in chunks if c['kind']=='pdf_page')
    assert table['text']==blocks[1]['text'] and table['text'].count('device_id')==1
    assert table['sources'][0]['page']==2


def test_config_validation(monkeypatch):
    for target,overlap in [('abc','50'),('40','5'),('100','60')]:
        monkeypatch.setenv('P18_CHUNK_TARGET',target);monkeypatch.setenv('P18_CHUNK_OVERLAP',overlap)
        with pytest.raises(ValueError):configuration()


def test_upload_auto_chunks_raw_persisted_and_idempotent(client):
    item=upload(client);doc=wait(client,item['id']);raw=copy.deepcopy(doc['result'])
    result=wait_chunks(client,item['id'])
    assert result['count']>0 and result['searchable'] is False
    assert result['chunks'][0]['sources'][0]['page']==1
    ids=[c['id'] for c in result['chunks']]
    route=f"/api/documents/{item['id']}/chunks"
    again=client.post(route,headers=HEADERS,json={'revision':1}).json()
    assert [c['id'] for c in again['chunks']]==ids and again['generation']==result['generation']
    assert client.get(f"/api/documents/{item['id']}").json()['result']==raw
    with main.connect() as c:
        stored=json.loads(c.execute('select body from chunk_runs where document_id=?',(item['id'],)).fetchone()[0])
        assert stored['normalized']['units']
        assert c.execute('select count(*) from chunks where document_id=?',(item['id'],)).fetchone()[0]==len(ids)
    assert client.get('/api/config').json()['indexing'] is False


def test_configuration_change_replaces_entire_generation(client,monkeypatch):
    item=upload(client,data=pdf_bytes('One complete statement. '*120));wait(client,item['id']);old=wait_chunks(client,item['id'])
    monkeypatch.setenv('P18_CHUNK_TARGET','100');monkeypatch.setenv('P18_CHUNK_OVERLAP','10')
    route=f"/api/documents/{item['id']}/chunks"
    stale=client.get(route).json()
    assert stale['status']=='stale' and stale['chunks']==[] and stale['count']==0
    client.post(route,headers=HEADERS,json={'revision':1});new=wait_chunks(client,item['id'])
    assert new['config']['target_chars']==100
    assert not ({c['id'] for c in old['chunks']}&{c['id'] for c in new['chunks']})
    assert all(c['config']==new['config'] for c in new['chunks'])
    with main.connect() as c:assert c.execute('select count(*) from chunks').fetchone()[0]==new['count']


def test_review_gate_and_risks_survive_chunking(client):
    from PIL import Image
    import pymupdf as fitz
    image=io.BytesIO();Image.new('RGB',(100,100),'black').save(image,format='PNG')
    pdf=fitz.open();pdf.new_page().insert_text((40,70),'Visible text')
    pdf.new_page().insert_image(fitz.Rect(20,20,500,700),stream=image.getvalue())
    item=upload(client,data=pdf.tobytes());pdf.close();doc=wait(client,item['id'])
    route=f"/api/documents/{item['id']}/chunks"
    assert client.get(route).json()['status']=='blocked'
    assert client.post(route,headers=HEADERS,json={'revision':1}).status_code==409
    client.post(f"/api/documents/{item['id']}/review",headers=HEADERS,json={'action':'accept','revision':1,'reviewer':'虚构测试员','checks':{'accept_incomplete':True}})
    result=wait_chunks(client,item['id'])
    assert all(c['risk']['incomplete'] and c['risk']['issues'][0]['page']==2 for c in result['chunks'])
    doc=main.get(item['id']);doc.update(state='review',revision=2);main.save(doc)
    assert client.get(route).json()['chunks']==[]
    assert client.post(route,headers=HEADERS,json={'revision':1}).status_code==409
    with main.connect() as c:assert c.execute('select count(*) from chunks').fetchone()[0]==0


def test_failed_document_cannot_chunk(client):
    item=upload(client,data=b'not pdf');wait(client,item['id'])
    assert client.get(f"/api/documents/{item['id']}/chunks").json()['status']=='blocked'
    assert client.post(f"/api/documents/{item['id']}/chunks",headers=HEADERS,json={'revision':1}).status_code==409


def test_delete_and_replacement_remove_chunk_associations(client):
    first=upload(client);wait(client,first['id']);wait_chunks(client,first['id'])
    replacement=upload(client,data=pdf_bytes('Replacement document'),mode='replace',replace_id=first['id'])
    wait(client,replacement['id']);wait_chunks(client,replacement['id'])
    assert client.get(f"/api/documents/{first['id']}/chunks").status_code==404
    with main.connect() as c:assert c.execute('select count(*) from chunks where document_id=?',(first['id'],)).fetchone()[0]==0
    client.delete(f"/api/documents/{replacement['id']}",headers=HEADERS)
    with main.connect() as c:
        assert c.execute('select count(*) from chunks').fetchone()[0]==0
        assert c.execute('select count(*) from chunk_runs').fetchone()[0]==0


def test_chunk_failure_does_not_change_document_quality_and_can_retry(client):
    with patch.object(main,'prepare',side_effect=ValueError('虚构切分失败')):
        item=upload(client);wait(client,item['id']);failed=wait_chunks(client,item['id'],'failed')
    assert failed['error']=='虚构切分失败' and failed['chunks']==[]
    assert main.get(item['id'])['quality']=='clear'
    client.post(f"/api/documents/{item['id']}/chunks",headers=HEADERS,json={'revision':1})
    assert wait_chunks(client,item['id'])['count']>0


def test_deleted_during_chunking_cannot_publish(client):
    entered,release=threading.Event(),threading.Event()
    original=main.prepare
    def paused(*args):
        entered.set();release.wait(5);return original(*args)
    with patch.object(main,'prepare',side_effect=paused):
        item=upload(client)
        try:
            assert entered.wait(5)
            client.delete(f"/api/documents/{item['id']}",headers=HEADERS)
        finally:release.set()
    for _ in range(100):
        if not main.CHUNK_ACTIVE:break
        time.sleep(.02)
    with main.connect() as c:assert c.execute('select count(*) from chunks').fetchone()[0]==0


def test_word_and_legacy_doc_actual_parse_and_chunks(client,tmp_path):
    if not soffice_path():pytest.skip('需要 LibreOffice 验证真实 Word 转换')
    source=tmp_path/'sample.docx';d=Document();d.add_heading('接口说明',level=1);d.add_paragraph('预约限制为 120 分钟。')
    table=d.add_table(rows=2,cols=2)
    for row,values in zip(table.rows,[['参数','说明'],['duration','最大120分钟']]):
        for cell,value in zip(row.cells,values):cell.text=value
    d.save(source)
    for ext,path in [('.docx',source),('.doc',convert(source,tmp_path/'legacy','doc:MS Word 97'))]:
        item=upload(client,name='sample'+ext,data=path.read_bytes());doc=wait(client,item['id'])
        assert doc['state']=='ready',doc
        result=wait_chunks(client,item['id'])
        if any(b['kind']=='table' for b in doc['result']['blocks']):
            table_chunk=next(c for c in result['chunks'] if c['kind']=='table')
            assert table_chunk['tables'][0]['rows'][1]==['duration','最大120分钟']
            assert table_chunk['sources'][0]['block_id']=='table-1'
        else:
            # The installed converter can flatten a DOC table. Do not invent a
            # table to make the assertion pass: retain text and disclose limits.
            assert ext=='.doc'
            assert 'duration' in ''.join(c['text'] for c in result['chunks'])
            assert any('不能恢复原始行列' in w for w in result['warnings'])
        assert all(s['variant']==('converted' if ext=='.doc' else 'original') for c in result['chunks'] for s in c['sources'])


def test_preview_entry_and_real_saved_text_endpoint(client):
    item=upload(client);wait(client,item['id']);result=wait_chunks(client,item['id'])
    assert 'Test reservation documentation' in result['chunks'][0]['text']
    assert '<option value="chunks">切分结果</option>' in client.get('/').text
    assert '/chunks' in client.get('/app.js').text


def test_inflight_configuration_change_never_publishes_old_result(client,monkeypatch):
    entered,release=threading.Event(),threading.Event();original=main.prepare
    def paused(*args):
        entered.set();release.wait(5);return original(*args)
    with patch.object(main,'prepare',side_effect=paused):
        item=upload(client)
        try:
            assert entered.wait(5)
            monkeypatch.setenv('P18_CHUNK_TARGET','120')
            monkeypatch.setenv('P18_CHUNK_OVERLAP','10')
        finally:release.set()
        for _ in range(200):
            if not main.CHUNK_ACTIVE:break
            time.sleep(.01)
    route=f"/api/documents/{item['id']}/chunks"
    assert client.get(route).json()['status']=='stale'
    with main.connect() as c:assert c.execute('select count(*) from chunks').fetchone()[0]==0
    client.post(route,headers=HEADERS,json={'revision':1})
    assert wait_chunks(client,item['id'])['config']['target_chars']==120


def test_database_migration_keeps_existing_metadata(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DATA',tmp_path);monkeypatch.setattr(main,'DB',tmp_path/'old.sqlite3')
    with sqlite3.connect(main.DB) as c:
        c.execute('CREATE TABLE documents (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
        c.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, document_id TEXT, action TEXT, at TEXT, revision INTEGER)')
        c.execute('INSERT INTO documents VALUES (?,?)',('old','{"state":"held"}'))
    main.initialize();main.initialize()
    with main.connect() as c:
        assert c.execute('select body from documents').fetchone()[0]=='{"state":"held"}'
        assert {'chunks','chunk_runs'} <= {r[0] for r in c.execute("select name from sqlite_master where type='table'")}


def test_chunk_output_survives_restart_without_regeneration(client):
    item=upload(client);wait(client,item['id']);first=wait_chunks(client,item['id'])
    import asyncio
    async def restart():
        async with main.lifespan(main.app):pass
    asyncio.run(restart())
    second=wait_chunks(client,item['id'])
    assert second['generation']==first['generation'] and second['chunks']==first['chunks']


def test_actual_pdf_table_retains_page_text_and_extracted_cells(tmp_path):
    import pymupdf as fitz
    pdf=fitz.open();page=pdf.new_page()
    for x in (50,200,350):page.draw_line((x,80),(x,170))
    for y in (80,110,140,170):page.draw_line((50,y),(350,y))
    for y,values in zip((100,130,160),[('Parameter','Description'),('duration','120 minutes'),('device_id','required')]):
        page.insert_text((60,y),values[0]);page.insert_text((210,y),values[1])
    path=tmp_path/'table.pdf';pdf.save(path);pdf.close()
    result=parse_pdf(path)
    assert result['blocks'][0]['tables']
    doc=sample(result['blocks'],ext='.pdf');doc['result']=result
    _,chunks=prepare(doc,configuration())
    assert chunks[0]['kind']=='pdf_page'
    assert chunks[0]['text']==result['blocks'][0]['text']
    assert chunks[0]['tables'][0]['rows'][1]==['duration','120 minutes']
    assert chunks[0]['sources'][0]['page']==1


def test_invalid_configuration_fails_preparation_not_parse(client,monkeypatch):
    monkeypatch.setenv('P18_CHUNK_TARGET','bad')
    item=upload(client);doc=wait(client,item['id'])
    assert doc['state']=='ready' and doc['quality']=='clear'
    result=client.get(f"/api/documents/{item['id']}/chunks").json()
    assert result['status']=='failed' and result['chunks']==[]
    monkeypatch.setenv('P18_CHUNK_TARGET','500')
    client.post(f"/api/documents/{item['id']}/chunks",headers=HEADERS,json={'revision':1})
    assert wait_chunks(client,item['id'])['count']>0


def test_fenced_content_does_not_create_fake_sections():
    blocks=[paragraph(1,'接口','接口',heading_level=1)]+[paragraph(i+2,t,'接口') for i,t in enumerate(['```markdown','# not a document heading','1 another code line','```','结束说明。'])]
    _,chunks=prepare(sample(blocks),configuration())
    assert all(c['section']=='接口' for c in chunks)
    assert '# not a document heading\n1 another code line' in next(c['text'] for c in chunks if c['kind']=='code')

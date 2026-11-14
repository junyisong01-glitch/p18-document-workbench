import io
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

import pymupdf as fitz
import pytest
from docx import Document
from fastapi.testclient import TestClient

from app import main
from app.parser import parse_pdf, parse_word, validate

HEADERS = {"X-P18-Client": "workbench"}


def pdf_bytes(text="Test reservation documentation"):
    doc = fitz.open();page=doc.new_page()
    if text:page.insert_text((50,70),text)
    data=doc.tobytes();doc.close();return data


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main,"DATA",tmp_path)
    monkeypatch.setattr(main,"DB",tmp_path / "test.sqlite3")
    with TestClient(main.app) as c:yield c
    deadline=time.time()+10
    while main.ACTIVE and time.time()<deadline:time.sleep(.05)


def upload(client, name="sample.pdf", data=None, **kwargs):
    response=client.post('/api/documents',files=[('files',(name,data or pdf_bytes(),'application/octet-stream'))],headers=HEADERS,data=kwargs)
    assert response.status_code==200,response.text
    return response.json()[0]


def wait(client,identifier):
    for _ in range(200):
        response=client.get(f'/api/documents/{identifier}')
        if response.status_code==200 and response.json()['state'] not in main.STATES:return response.json()
        time.sleep(.05)
    raise AssertionError("processing timed out")

def settle(client,identifier):
    """Wait for the background chunk job: it saves its own copy of the record,
    so editing the document while it runs can lose the edit or bump revision."""
    for _ in range(400):
        status=client.get(f'/api/documents/{identifier}/chunks').json()['status']
        if status not in {'not_started','queued','processing'} and not main.CHUNK_ACTIVE:return
        time.sleep(.05)
    raise AssertionError("chunking did not settle")


def test_pdf_upload_real_parse_and_preview(client):
    item=upload(client);doc=wait(client,item['id'])
    assert doc['state']=='ready' and doc['quality']=='clear'
    assert 'reservation' in doc['result']['blocks'][0]['text']
    assert client.get(f"/api/documents/{doc['id']}/preview/original/1").headers['content-type']=='image/png'
    assert client.get('/api/config').json()['indexing'] is False


def test_duplicate_content_and_name_conflict(client):
    content=pdf_bytes();first=upload(client,data=content);wait(client,first['id'])
    assert upload(client,name='renamed.pdf',data=content)['status']=='duplicate'
    assert upload(client,data=pdf_bytes('Changed content'))['status']=='conflict'
    assert upload(client,data=pdf_bytes('Different content'),mode='keep')['status']=='accepted'
    for d in client.get('/api/documents').json():wait(client,d['id'])


def test_failed_replacement_preserves_old(client):
    first=upload(client);wait(client,first['id'])
    second=upload(client,data=b'%PDF-invalid',mode='replace',replace_id=first['id']);doc=wait(client,second['id'])
    assert doc['state']=='failed'
    assert client.get(f"/api/documents/{first['id']}").json()['state']=='ready'


def test_successful_replacement_and_delete_cleans_all(client):
    first=upload(client);wait(client,first['id'])
    second=upload(client,data=pdf_bytes('New valid content'),mode='replace',replace_id=first['id']);wait(client,second['id'])
    assert client.get(f"/api/documents/{first['id']}").status_code==404
    assert client.delete(f"/api/documents/{second['id']}",headers=HEADERS).status_code==200
    assert not main.folder_for(first['id']).exists()
    assert not main.folder_for(second['id']).exists()
    assert client.get('/api/documents').json()==[]


def test_mixed_pdf_review_and_revision_guard(client):
    from PIL import Image
    image=io.BytesIO();Image.new('RGB',(100,100),'black').save(image,format='PNG')
    pdf=fitz.open();pdf.new_page().insert_text((40,70),'Visible text')
    pdf.new_page().insert_image(fitz.Rect(20,20,500,700),stream=image.getvalue())
    item=upload(client,data=pdf.tobytes());pdf.close();doc=wait(client,item['id'])
    assert doc['state']=='review' and doc['result']['issues'][0]['page']==2
    route=f"/api/documents/{item['id']}/review"
    assert client.post(route,headers=HEADERS,json={'reviewer':'测试审核员','action':'accept','revision':99}).status_code==409
    assert client.post(route,headers=HEADERS,json={'reviewer':'测试审核员','action':'hold','revision':1}).json()['state']=='held'
    result=client.post(route,headers=HEADERS,json={'reviewer':'测试审核员','action':'accept','revision':1,'checks':{'accept_incomplete':True}}).json()
    assert result['state']=='ready' and result['quality']=='review' and result['issues_count']==1
    assert client.get(f"/api/documents/{item['id']}").json()['events'][-1]['action']=='review_accept'


def test_blank_invalid_and_retry(client):
    blank=upload(client,data=pdf_bytes(''));assert wait(client,blank['id'])['state']=='failed'
    bad=upload(client,name='bad.pdf',data=b'not pdf');doc=wait(client,bad['id']);assert doc['quality']=='failed'
    route=f"/api/documents/{bad['id']}/retry"
    client.post(route,headers=HEADERS);client.post(route,headers=HEADERS)
    assert wait(client,bad['id'])['revision']==2


def test_limits_and_csrf(client):
    assert client.post('/api/documents',files=[('files',('a.pdf',pdf_bytes()))]).status_code==403
    assert client.post('/api/documents',headers={**HEADERS,'Origin':'https://foreign.example'},files=[('files',('a.pdf',pdf_bytes()))]).status_code==403
    too_many=[('files',(f'{i}.pdf',pdf_bytes())) for i in range(21)]
    assert client.post('/api/documents',headers=HEADERS,files=too_many).status_code==400
    assert upload(client,name='a.txt',data=b'hello')['status']=='rejected'
    with patch.object(main,'MAX_FILE',10):assert upload(client,data=b'0'*11)['status']=='rejected'
    with patch.object(main,'MAX_BATCH',5):
        assert client.post('/api/documents',headers=HEADERS,files=[('files',('a.pdf',b'123456'))]).status_code==400


def test_encryption_and_page_limit(tmp_path):
    p=tmp_path/'secret.pdf';pdf=fitz.open();pdf.new_page();pdf.save(p,encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='owner',user_pw='password');pdf.close()
    with pytest.raises(ValueError,match='密码'):validate(p,'.pdf')
    p=tmp_path/'large.pdf';pdf=fitz.open()
    for _ in range(201):pdf.new_page()
    pdf.save(p);pdf.close()
    with pytest.raises(ValueError,match='200'):validate(p,'.pdf')


def test_word_tables_code_and_merge(tmp_path):
    doc=Document();doc.add_heading('API',1);doc.add_paragraph('if ok:\n    return value')
    table=doc.add_table(rows=2,cols=2);table.cell(0,0).text='name';table.cell(0,1).text='type';table.cell(1,0).text='id';table.cell(1,1).text='string'
    p=tmp_path/'simple.docx';doc.save(p);validate(p,'.docx');result=parse_word(p)
    assert not result['issues']
    assert '    return value' in result['blocks'][1]['text']
    assert result['blocks'][2]['tables'][0]['rows'][1]==['id','string']
    table.cell(1,0).merge(table.cell(1,1));doc.save(p)
    assert any(i['kind']=='table' and i['block']=='table-1' for i in parse_word(p)['issues'])


def test_delete_running_never_resurrects(client):
    with patch.object(main.POOL,'submit'):
        item=upload(client)
    assert client.delete(f"/api/documents/{item['id']}",headers=HEADERS).status_code==200
    main.run_job(item['id'],1)
    assert client.get('/api/documents').json()==[]
    assert not main.folder_for(item['id']).exists()


def test_delete_failure_excludes_content_and_retries(client):
    item=upload(client);wait(client,item['id'])
    with patch.object(main.shutil,'rmtree',side_effect=PermissionError()):
        assert client.delete(f"/api/documents/{item['id']}",headers=HEADERS).status_code==500
    assert client.get(f"/api/documents/{item['id']}/file/original").status_code==404
    assert client.delete(f"/api/documents/{item['id']}",headers=HEADERS).status_code==200


def test_safe_filename_and_persistence(client):
    item=upload(client,name='../../outside.pdf');doc=wait(client,item['id'])
    assert doc['name']=='outside.pdf'
    assert main.get(item['id'])['result']['characters']>0
    assert not (main.DATA.parent/'outside.pdf').exists()


def test_restart_marks_pending_failed(client):
    with patch.object(main.POOL,'submit'):item=upload(client)
    import asyncio
    async def restart():
        async with main.lifespan(main.app):pass
    asyncio.run(restart())
    assert main.get(item['id'])['state']=='failed'


def test_doc_conversion_missing_dependency(tmp_path,monkeypatch):
    from app import parser
    monkeypatch.setattr(parser,'soffice_path',lambda:None)
    with pytest.raises(ValueError,match='未配置'):parser.convert(tmp_path/'x.doc',tmp_path/'out','docx')


def test_entry_assets_resolve_from_http_and_file_paths(client):
    import re
    from urllib.parse import urlsplit
    html = client.get('/').text
    script_src = re.search(r'<script src="([^"]+)"', html).group(1)
    style_src = re.search(r'<link rel="stylesheet" href="([^"]+)"', html).group(1)
    assert urlsplit(style_src).path == 'style.css' and urlsplit(script_src).path == 'app.js'
    assert client.get('/style.css').status_code == 200
    script = client.get('/' + script_src)
    assert script.status_code == 200 and 'text/javascript' in script.headers['content-type']
    assert "window.location.protocol === 'file:'" in script.text


def test_launcher_reuses_healthy_server():
    from scripts import launch
    with patch.object(launch, 'probe', return_value={'config':{'workbench_version':launch.VERSION,'data_directory':str(launch.ROOT/'runtime')},'semantic':{'enabled':False}}), patch.object(launch.subprocess, 'Popen') as spawn:
        launch.launch(False)
        spawn.assert_not_called()


def test_word_preview_preserves_chinese(tmp_path):
    """Exercise the actual converter: successful PDF creation alone is insufficient."""
    from app.parser import convert, soffice_path
    if not soffice_path():
        pytest.skip('LibreOffice is not installed')
    source = tmp_path / 'chinese.docx'
    document = Document()
    document.add_heading('虚构设备预约接口说明', 0)
    document.add_paragraph('预约时长不得超过 120 分钟。')
    table = document.add_table(rows=2, cols=2)
    for row, values in zip(table.rows, [('参数', '说明'), ('device_id', '设备编号')]):
        for cell, value in zip(row.cells, values):
            cell.text = value
    document.save(source)
    with fitz.open(convert(source, tmp_path / 'preview', 'pdf')) as pdf:
        text = ''.join(page.get_text() for page in pdf)
        for expected in ['虚构设备预约接口说明', '预约时长不得超过', '参数', '设备编号', 'device_id']:
            assert expected in text


def test_clear_auto_build_intent_and_failed_blocked(client):
    item=upload(client);doc=wait(client,item['id'])
    assert doc['admission']['eligible'] and doc['build']['status']=='waiting'
    assert doc['build']['reason']=='index_disabled' and not doc['build']['searchable']
    intent=doc['build']['request_id']
    main.save(main.get(item['id']))
    assert main.get(item['id'])['build']['request_id']==intent
    bad=upload(client,name='invalid.pdf',data=b'invalid');failed=wait(client,bad['id'])
    assert not failed['admission']['eligible'] and failed['build']['request_id'] is None
    assert failed['admission']['categories'][0]['code']=='unusable'


@pytest.mark.parametrize('kind,key', [('image','accept_incomplete'),('table','structure_correct'),('characters','text_correct'),('future_issue','structure_correct'),('preview','preview_checked')])
def test_category_review_guard(client,kind,key):
    item=upload(client);doc=wait(client,item['id'])
    doc.update(state='review',quality='review')
    if kind=='preview':doc['result']['preview_warnings']=['预览生成失败']
    else:doc['result']['issues']=[{'kind':kind,'message':'核对','page':1}]
    main.save(doc)
    route=f"/api/documents/{item['id']}/review"
    assert client.post(route,headers=HEADERS,json={'reviewer':'测试审核员','action':'accept','revision':1}).status_code==400
    held=client.post(route,headers=HEADERS,json={'reviewer':'测试审核员','action':'hold','revision':1,'outcome':'incorrect'}).json()
    assert held['state']=='held' and held['build']['status']=='blocked'
    assert held['review_decision']['outcome']=='incorrect'
    accepted=client.post(route,headers=HEADERS,json={'reviewer':'测试审核员','action':'accept','revision':1,'checks':{key:True}}).json()
    assert accepted['admission']['eligible'] and accepted['build']['status']=='waiting'
    assert accepted['quality']=='review' and accepted['review_decision']['revision']==1
    assert client.post(route,headers=HEADERS,json={'reviewer':'测试审核员','action':'accept','revision':1,'checks':{key:True}}).status_code==409


def test_multiple_categories_require_all_checks_and_current_revision(client):
    item=upload(client);doc=wait(client,item['id']);doc.update(state='review',quality='review')
    doc['result']['issues']=[{'kind':'image'}, {'kind':'table'}, {'kind':'characters'}]
    main.save(doc);route=f"/api/documents/{item['id']}/review"
    assert client.post(route,headers=HEADERS,json={'reviewer':'测试审核员','action':'accept','revision':1,'checks':{'accept_incomplete':True}}).status_code==400
    checks={'accept_incomplete':True,'structure_correct':True,'text_correct':True}
    assert client.post(route,headers=HEADERS,json={'reviewer':'测试审核员','action':'accept','revision':1,'checks':checks}).json()['build']['status']=='waiting'
    doc=main.get(item['id']);doc['revision']=2;main.save(doc)
    assert not main.get(item['id'])['admission']['eligible']


def test_legacy_acceptance_requires_category_review_on_restart(client):
    item=upload(client);doc=wait(client,item['id']);doc['result']['issues']=[{'kind':'image'}]
    doc['quality']='review';main.save(doc)
    import asyncio
    async def restart():
        async with main.lifespan(main.app):pass
    asyncio.run(restart())
    current=main.get(item['id'])
    assert current['state']=='review' and current['build']['status']=='blocked'


def test_preview_failure_goes_to_review_without_losing_text(client):
    result={'blocks':[], 'issues':[], 'characters':10,'preview_warnings':['预览失败']}
    # Run through the actual worker-completion path while simulating converter output.
    with patch.object(main.POOL,'submit'):item=upload(client)
    class Worker:
        returncode=0
        def wait(self,timeout=None):
            import json
            (main.folder_for(item['id'])/'result.json').write_text(json.dumps(result))
    with patch.object(main.subprocess,'Popen',return_value=Worker()):main.run_job(item['id'],1)
    doc=main.get(item['id'])
    assert doc['state']=='review' and doc['characters']==10
    assert doc['admission']['categories']==[{'code':'preview','label':'仅预览异常'}]


def test_reviewer_required_and_history_append_only(client):
    item=upload(client);doc=wait(client,item['id']);settle(client,item['id'])
    doc.update(state='review',quality='review')
    doc['result']['issues']=[{'kind':'image','message':'图片未识别','page':1}]
    main.save(doc);route=f"/api/documents/{item['id']}/review"
    for reviewer in [None, '', '  ', 123, 'x'*81]:
        assert client.post(route,headers=HEADERS,json={'action':'hold','revision':1,'reviewer':reviewer}).status_code==400
    assert main.get(item['id'])['state']=='review'
    assert client.get(f"/api/documents/{item['id']}").json()['review_pending']
    held=client.post(route,headers=HEADERS,json={'action':'hold','revision':1,'reviewer':'  甲  ','outcome':'uncertain','note':'需再次确认'}).json()
    assert not held['review_pending'] and held['review_completed'] and held['state']=='held'
    accepted=client.post(route,headers=HEADERS,json={'action':'accept','revision':1,'reviewer':'乙','checks':{'accept_incomplete':True},'note':'接受遗漏'}).json()
    assert not accepted['review_pending'] and accepted['review_completed']
    assert accepted['admission']['incomplete'] and accepted['quality']=='review'
    events=client.get(f"/api/documents/{item['id']}").json()['events']
    reviews=[e['payload'] for e in events if e['action'].startswith('review_')]
    assert [r['reviewer'] for r in reviews]==['甲','乙']
    assert reviews[0]['note']=='需再次确认' and reviews[1]['issues'][0]['page']==1
    assert reviews[1]['requirements'][0]['key']=='accept_incomplete'
    # Direct fixture edits follow the same lock discipline as production routes.
    with main.LOCK:
        doc=main.get(item['id']);doc.update(state='review',revision=2);main.save(doc)
    updated=client.get(f"/api/documents/{item['id']}").json()
    assert updated['review_pending'] and not updated['review_completed']
    assert len([e for e in updated['events'] if e['action'].startswith('review_')])==2


def test_old_review_without_name_stays_completed(client):
    item=upload(client);doc=wait(client,item['id']);settle(client,item['id'])
    doc.update(quality='review',review_decision={'revision':1,'outcome':'accepted','checks':{'structure_correct':True}})
    doc['result']['issues']=[{'kind':'table','message':'检查表格'}];main.save(doc)
    main.event(doc,'review_accept')
    import asyncio
    async def restart():
        async with main.lifespan(main.app):pass
    asyncio.run(restart())
    response=client.get(f"/api/documents/{item['id']}").json()
    assert response['state']=='ready' and response['review_completed'] and not response['review_pending']
    assert response['events'][-1]['payload'] is None

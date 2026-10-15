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
    assert client.post(route,headers=HEADERS,json={'action':'accept','revision':99}).status_code==409
    assert client.post(route,headers=HEADERS,json={'action':'hold','revision':1}).json()['state']=='held'
    result=client.post(route,headers=HEADERS,json={'action':'accept','revision':1}).json()
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
    html = client.get('/').text
    assert 'href="style.css"' in html and 'src="app.js"' in html
    assert client.get('/style.css').status_code == 200
    script = client.get('/app.js')
    assert script.status_code == 200 and 'text/javascript' in script.headers['content-type']
    assert "window.location.protocol === 'file:'" in script.text


def test_launcher_reuses_healthy_server():
    from scripts import launch
    with patch.object(launch, 'healthy', return_value=True), patch.object(launch.subprocess, 'Popen') as spawn:
        launch.launch(False)
        spawn.assert_not_called()

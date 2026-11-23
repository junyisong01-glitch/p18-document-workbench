import json
import time

from app.business import match_title
from test_business_workflow import rig


def upload(r,who,old,version='V2',**extra):
    data={'name':'修订样例','code':'SAMPLE','version':version,'department':'研发部','classification':'内部','replaces':old,**extra}
    return r.c.post('/api/business/upload',headers=r.h[who],files={'file':('example.docx',b'fictional-replacement')},data={'metadata_json':json.dumps(data)})


def test_upload_match_only_returns_documents_user_can_update(rig):
    r=rig;owned=r.create();peer=r.create(owner='qa');hidden=r.create(owner='prd',dept='生产制造部');pending=r.create(status='submitted')
    body={'name':'虚构样例_V2.docx','department':'研发部'}
    def match(who,data=body):return r.c.post('/api/business/upload-match',headers=r.h[who],json=data)
    rows=match('rd').json()
    assert {row['id'] for row in rows}=={owned,pending}
    assert next(row for row in rows if row['id']==pending)['can_replace'] is False
    assert {row['id'] for row in match('head').json()}=={owned,peer,pending}
    assert hidden not in match('head').text
    assert match('prd').status_code==422 and match('guest').status_code==403
    assert match('rd',{**body,'name':'完全不同','code':'SAMPLE'}).json()
    assert match_title('QC-RD-SUP-025_测试记录_V2.0.docx')==match_title('测试记录')
    assert match_title('V1.3.1 技术设计')!=match_title('V2.0 技术设计')
    assert r.action(owned,'head','archive').status_code==200
    assert owned not in {row['id'] for row in match('rd').json()}


def test_matched_version_change_is_rejected_before_upload(rig):
    r=rig;old=r.create();assert r.action(old,'boss','make_internal').status_code==200
    assert upload(r,'rd',old,replaces_expected=0).status_code==409
    assert r.q.business_read(old)['status']=='published' and not r.q.business_read(old)['archived']
    response=upload(r,'rd',old,replaces_expected=1)
    assert response.status_code==200,response.text
    assert r.q.business_read(old)['archived']
    assert response.json()['workflow']['status']=='published'
    assert upload(r,'rd',old,replaces_expected=1).status_code==409


def test_failed_upload_is_preserved_when_checked_replacement_auto_publishes(rig):
    r=rig;old=r.create(status='submitted');d=r.q.get(old);d['state']='failed';r.q.save(d)
    assert upload(r,'qa',old,version='V1').status_code in {403,409}
    response=upload(r,'head',old,version='V1',replaces_expected=0)
    assert response.status_code==200,response.text
    new=response.json()['id'];previous=r.q.business_read(old);current=r.q.business_read(new)
    assert previous['status']=='withdrawn' and previous['archived']
    assert current['status']=='published' and current['series']==previous['series']
    assert current['replaces'] is None and current['revises']==old
    assert r.q.get(old)['state']=='failed'
    assert r.c.get('/api/business/documents/'+old+'/audit',headers=r.h['head']).json()[-1]['action']=='replaced_submission'


def test_withdrawn_owner_can_remove_and_restore_record_only(rig):
    r=rig;doc=r.create(status='submitted')
    assert r.action(doc,'rd','trash').status_code==403
    assert r.action(doc,'rd','withdraw').status_code==200
    assert r.action(doc,'qa','trash').status_code in {403,404}
    assert r.action(doc,'rd','trash').status_code==200
    assert r.c.get('/api/documents/'+doc,headers=r.h['rd']).status_code==200
    assert r.c.get('/api/documents/'+doc,headers=r.h['qa']).status_code==404
    assert r.action(doc,'rd','restore').status_code==200
    assert r.q.business_read(doc)['status']=='withdrawn'
    assert r.action(doc,'rd','publish').status_code==409
    response=upload(r,'rd',doc,version='V1')
    assert response.status_code==200 and r.q.business_read(doc)['archived']


def test_borrowers_are_minimal_internal_and_require_document_manager(rig):
    r=rig;doc=r.create();url='/api/business/documents/'+doc+'/borrowers'
    assert r.c.get(url,headers=r.h['rd']).status_code==404
    assert r.c.get(url,headers=r.h['otherhead']).status_code==404
    assert r.c.get(url,headers=r.h['guest']).status_code==404
    response=r.c.get(url,headers=r.h['head']);assert response.status_code==200
    rows=response.json();assert 'guest' not in {p['username'] for p in rows}
    assert all(set(p)=={'username','department','job','role','granted','expires_at'} for p in rows)
    assert not any(p['granted'] for p in rows)
    assert r.action(doc,'head','share',username='prd').status_code==200
    rows=r.c.get(url,headers=r.h['head']).json();assert next(p for p in rows if p['username']=='prd')['granted']
    with r.q.connect()as c:c.execute('UPDATE business_grants SET expires=? WHERE document_id=?',(time.time()-10,doc))
    assert not any(p['granted'] for p in r.c.get(url,headers=r.h['head']).json())
    secret=r.create(restricted=True);assert r.c.get('/api/business/documents/'+secret+'/borrowers',headers=r.h['head']).status_code in {403,404}
    assert r.c.get('/api/business/documents/'+secret+'/borrowers',headers=r.h['boss']).status_code==200
    pending=r.create(status='submitted');assert r.c.get('/api/business/documents/'+pending+'/borrowers',headers=r.h['head']).status_code==409


def test_nonexistent_question_can_be_closed_with_reason_and_reopened(rig):
    r=rig;gap=r.c.post('/api/business/gaps',headers=r.h['rd'],json={'question':'不存在的演示工单'}).json()
    url='/api/business/gaps/'+gap['id'];body={'expected':0,'status':'closed'}
    assert r.c.put(url,headers=r.h['head'],json=body).status_code==422
    body['note']='已核对，该工单不存在。请确认编号。'
    assert r.c.put(url,headers=r.h['rd'],json=body).status_code==403
    assert r.c.put(url,headers=r.h['head'],json=body).status_code==200
    result=r.c.get('/api/business/gaps',headers=r.h['rd']).json()[0]
    assert result['status']=='closed' and result['document'] is None and result['note']==body['note']
    assert r.c.put(url,headers=r.h['head'],json={'expected':1,'status':'in_progress','note':'员工补充了正确编号，重新处理。'}).status_code==200

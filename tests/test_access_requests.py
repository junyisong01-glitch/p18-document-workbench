import json
import time
import pytest
from tests.test_business_workflow import rig

PATH='/api/business/access-requests'

def create(r,who='prd',department='研发部',question='错误码如何处理？'):
    return r.c.post(PATH,headers=r.h[who],json={'question':question,'purpose':'现场排障','department':department})

def decide(r,req,who='head',action='approve',doc=None,**kw):
    body={'expected':req['version'],'action':action,**kw}
    if doc:body.update(document_id=doc,document_version=r.q.business_read(doc)['version'])
    return r.c.post(PATH+'/'+req['id']+'/decision',headers=r.h[who],json=body)

def listing(r,who):
    response=r.c.get(PATH,headers=r.h[who]);assert response.status_code==200,response.text
    return response.json()

def test_request_routing_approval_revocation_and_no_title_leak(rig):
    r=rig;doc=r.create();req=create(r).json()
    assert len(listing(r,'head'))==1
    assert listing(r,'otherhead')==[] and listing(r,'rd')==[]
    assert listing(r,'prd')[0]['document'] is None
    assert r.c.get('/api/documents/'+doc,headers=r.h['prd']).status_code==404
    assert decide(r,req,who='otherhead',doc=doc).status_code==404
    assert decide(r,req,who='prd',doc=doc).status_code==403
    approved=decide(r,req,doc=doc);assert approved.status_code==200,approved.text
    mine=listing(r,'prd')[0]
    assert mine['status']=='approved' and mine['access_available'] and mine['document']['id']==doc
    assert r.c.get('/api/documents/'+doc,headers=r.h['prd']).status_code==200
    assert r.action(doc,'prd','share',username='qa').status_code==403
    assert decide(r,req,doc=doc).status_code==409
    assert r.action(doc,'head','revoke_share',username='prd').status_code==200
    mine=listing(r,'prd')[0]
    assert mine['status']=='approved' and mine['document'] is None and not mine['access_available']
    assert doc not in json.dumps(mine)
    with r.q.connect() as c:
        event=c.execute("SELECT body FROM business_events WHERE document_id=? AND action='share'",(doc,)).fetchone()
        assert json.loads(event[0])['request_id']==req['id']
        assert c.execute('SELECT COUNT(*) FROM access_request_events WHERE request_id=?',(req['id'],)).fetchone()[0]==2

def test_duplicate_cancel_reject_and_guest(rig):
    r=rig
    assert create(r,'guest').status_code==403
    assert r.c.get(PATH,headers=r.h['guest']).status_code==403
    req=create(r).json();assert create(r).json()['id']==req['id']
    assert decide(r,req,action='cancel').status_code==403
    assert decide(r,req,who='prd',action='cancel').status_code==200
    assert decide(r,req,action='reject').status_code==409
    req2=create(r).json();assert req2['id']!=req['id']
    assert decide(r,req2,action='reject').status_code==200
    assert listing(r,'prd')[0]['status']=='rejected'
    assert create(r,department='不存在').status_code==422
    assert r.c.post(PATH,headers=r.h['prd'],json={'question':'  ','purpose':' ','department':'研发部'}).status_code==422
    assert r.c.post(PATH,headers=r.h['prd'],json={'question':'问题','purpose':'用途','department':'研发部','owner':'boss'}).status_code==422

@pytest.mark.parametrize('case',['restricted','unpublished','archived','deleted','wrong_department','stale_document','no_index','disabled_owner','moved_owner'])
def test_approval_revalidates_authority_and_state_atomically(rig,case):
    r=rig;doc=r.create(restricted=case=='restricted',status='submitted' if case=='unpublished' else 'published',dept='生产制造部' if case=='wrong_department' else '研发部');req=create(r).json()
    if case in ['archived','deleted']:
        with r.q.connect() as c:
            b=r.q.business_read(doc);b[case]=True;c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b),doc))
    if case=='no_index':r.index_states[doc]={'status':'failed','searchable':False}
    if case in ['disabled_owner','moved_owner']:
        with r.q.connect() as c:
            if case=='disabled_owner':c.execute("UPDATE library_accounts SET active=0 WHERE username='prd'")
            else:c.execute("UPDATE business_profiles SET department='财务部' WHERE username='prd'")
    if case=='stale_document':
        response=r.c.post(PATH+'/'+req['id']+'/decision',headers=r.h['head'],json={'action':'approve','expected':0,'document_id':doc,'document_version':999})
    else:response=decide(r,req,doc=doc)
    assert response.status_code in [404,409],response.text
    with r.q.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM business_grants WHERE document_id=?',(doc,)).fetchone()[0]==0
        assert c.execute('SELECT status FROM access_requests WHERE id=?',(req['id'],)).fetchone()[0]=='pending'

def test_boss_restricted_and_existing_grant_expiry_preserved(rig):
    r=rig;doc=r.create(restricted=True);req=create(r).json()
    assert r.action(doc,'boss','share',username='prd').status_code==200
    assert decide(r,req,who='boss',doc=doc,days=1).status_code==200
    with r.q.connect() as c:assert c.execute('SELECT expires FROM business_grants WHERE document_id=?',(doc,)).fetchone()[0] is None
    own=create(r,'head',question='主管自己的需求').json()
    assert decide(r,own,doc=doc).status_code==403

def test_expiration_hides_document_from_applicant(rig):
    r=rig;doc=r.create();req=create(r).json()
    assert decide(r,req,doc=doc,days=1).status_code==200
    with r.q.connect() as c:c.execute('UPDATE business_grants SET expires=? WHERE document_id=?',(time.time()-1,doc))
    assert listing(r,'prd')[0]['document'] is None
    assert r.c.get('/api/documents/'+doc,headers=r.h['prd']).status_code==404

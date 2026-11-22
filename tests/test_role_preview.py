"""Real authentication/SQLite boundaries for role preview and submitted gaps."""
import json
from test_business_workflow import rig


def post(r, who, question='网关轮换证书后如何恢复连接？'):
    return r.c.post('/api/business/gaps', headers=r.h[who], json={'question': question})


def listing(r, who):
    return r.c.get('/api/business/gaps', headers=r.h[who])


def test_gap_is_opt_in_dept_scoped_and_idempotent(rig):
    r=rig
    assert listing(r,'rd').json()==[]
    first=post(r,'rd').json()
    assert post(r,'rd').json()['reporter_count']==1
    second=post(r,'qa').json()
    assert second['id']==first['id'] and second['reporter_count']==2
    assert listing(r,'ops').json()==[]
    assert len(listing(r,'head').json())==1
    assert listing(r,'otherhead').json()==[]
    third=post(r,'prd').json()
    assert third['id']!=first['id']
    assert listing(r,'guest').status_code==403
    assert post(r,'guest').status_code==403
    assert listing(r,'boss').status_code==403
    assert post(r,'boss').status_code==403
    counts=r.c.get('/api/business/gaps/summary',headers=r.h['boss'])
    assert counts.status_code==200
    assert all(set(row)=={'department','status','total'} for row in counts.json())
    assert '网关' not in counts.text
    assert r.c.get('/api/business/gaps/summary',headers=r.h['rd']).status_code==403
    assert post(r,'rd','  ').status_code==422
    assert r.c.post('/api/business/gaps',headers=r.h['rd'],json={'question':'hello','department':'生产制造部'}).status_code==422


def test_gap_changes_require_supervisor_and_published_evidence(rig):
    r=rig;gap=post(r,'rd').json();url='/api/business/gaps/'+gap['id']
    body={'expected':0,'status':'in_progress','note':'正在补充接入说明'}
    assert r.c.put(url,headers=r.h['rd'],json=body).status_code==403
    assert r.c.put(url,headers=r.h['otherhead'],json=body).status_code==404
    assert r.c.put(url,headers=r.h['head'],json=body).status_code==200
    assert r.c.put(url,headers=r.h['head'],json=body).status_code==409
    body.update(expected=1,status='resolved')
    assert r.c.put(url,headers=r.h['head'],json=body).status_code==422
    pending=r.create(status='submitted');body['document_id']=pending
    assert r.c.put(url,headers=r.h['head'],json=body).status_code==404
    doc=r.create();body['document_id']=doc
    done=r.c.put(url,headers=r.h['head'],json=body)
    assert done.status_code==200 and done.json()['document']['id']==doc
    assert listing(r,'rd').json()[0]['document']['id']==doc
    assert r.action(doc,'head','archive').status_code==200
    assert listing(r,'rd').json()[0]['document'] is None


def test_linked_restricted_document_never_leaks_to_reporter(rig):
    r=rig;gap=post(r,'rd').json();doc=r.create(owner='head',restricted=True)
    assert r.action(doc,'boss','share',username='head').status_code==200
    response=r.c.put('/api/business/gaps/'+gap['id'],headers=r.h['head'],json={'expected':0,'status':'resolved','document_id':doc})
    assert response.status_code==200
    own=listing(r,'rd').json()[0]
    assert own['document'] is None and 'document_id' not in own
    assert doc not in json.dumps(own)


def test_company_internal_is_not_external_public_and_revokes_now(rig):
    r=rig;doc=r.create()
    assert r.action(doc,'head','make_internal').status_code==403
    assert r.action(doc,'boss','make_internal').status_code==200
    assert r.c.get('/api/documents/'+doc,headers=r.h['prd']).status_code==200
    assert r.c.get('/api/documents/'+doc,headers=r.h['guest']).status_code==404
    assert r.action(doc,'boss','make_public').status_code==200
    assert not r.q.business_read(doc)['company_internal']
    assert r.c.get('/api/documents/'+doc,headers=r.h['guest']).status_code==200
    assert r.action(doc,'boss','make_internal').status_code==200
    assert not r.q.business_read(doc)['company_public']
    assert r.c.get('/api/documents/'+doc,headers=r.h['guest']).status_code==404
    assert r.action(doc,'boss','revoke_internal').status_code==200
    assert r.c.get('/api/documents/'+doc,headers=r.h['prd']).status_code==404
    secret=r.create(restricted=True)
    assert r.action(secret,'boss','make_internal').status_code==409
    assert r.action(secret,'boss','make_public').status_code==409


def test_stale_guest_grant_does_not_expose_internal_records(rig):
    r=rig;doc=r.create()
    with r.q.connect()as c:c.execute('INSERT INTO business_grants VALUES (?,?,NULL)',(doc,'guest'))
    assert r.c.get('/api/documents/'+doc,headers=r.h['guest']).status_code==404


def test_new_pages_support_direct_open_and_refresh(rig):
    for route in ['/workbench','/knowledge-gaps']:
        response=rig.c.get(route,headers=rig.h['rd'])
        assert response.status_code==200 and 'text/html' in response.headers['content-type']

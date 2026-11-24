import json
import time
import pytest
from tests.test_business_workflow import rig

PATH='/api/business/access-requests'

@pytest.fixture(autouse=True)
def local_review_stub(monkeypatch):
    monkeypatch.setattr('app.access_recommendations.classify', lambda question, purpose, items: ({}, False))


def create(r,who='prd',department='研发部',question='错误码如何处理？'):
    return r.c.post(PATH,headers=r.h[who],json={'question':question,'purpose':'现场排障','department':department})

def decide(r,req,who='head',action='approve',doc=None,**kw):
    body={'expected':req['version'],'action':action,**({'note':'用途不符合本次授权条件'} if action=='reject' else {}),**kw}
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


def test_recommendations_are_reviewer_only_and_filtered_before_search(rig,monkeypatch):
    from types import SimpleNamespace
    r=rig;doc=r.create();secret=r.create(restricted=True);other=r.create(dept='生产制造部');draft=r.create(status='submitted');req=create(r).json()
    seen=[]
    def search(question,**kw):
        seen.extend(d for d in [doc,secret,other,draft] if kw['document_filter'](r.q.get(d)))
        assert kw['mode']=='hybrid'
        # Even an unexpected search result cannot escape the post-search gate.
        return {'results':[{'document_id':d,'text':'排查设备离线。','section':'排障步骤'} for d in [secret,other,draft,doc,doc]]}
    monkeypatch.setattr(r.q,'require_semantic',lambda:SimpleNamespace(search=search))
    def review(question,purpose,items):
        assert [item['id'] for item in items]==[doc]
        return {},True
    monkeypatch.setattr('app.access_recommendations.classify',review)
    path=PATH+'/'+req['id']+'/recommendations'
    for who in ['prd','rd','otherhead','guest']:
        assert r.c.get(path,headers=r.h[who]).status_code in [403,404]
    assert seen==[]
    response=r.c.get(path,headers=r.h['head']);assert response.status_code==200,response.text
    assert seen==[doc]
    assert [d['id'] for d in response.json()['items']]==[doc]
    assert response.json()['items'][0]['excerpt']=='排查设备离线。'
    assert decide(r,req,action='reject').status_code==200
    assert r.c.get(path,headers=r.h['head']).status_code==409


def test_recommendations_recheck_changes_and_do_not_assert_global_absence(rig,monkeypatch):
    from types import SimpleNamespace
    r=rig;doc=r.create();req=create(r).json()
    def search(question,**kw):
        assert kw['document_filter'](r.q.get(doc))
        with r.q.connect() as c:
            b=r.q.business_read(doc);b['archived']=True
            c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b),doc))
        return {'results':[{'document_id':doc,'text':'不再可以显示'}]}
    monkeypatch.setattr(r.q,'require_semantic',lambda:SimpleNamespace(search=search))
    result=r.c.get(PATH+'/'+req['id']+'/recommendations',headers=r.h['head']).json()
    assert result['items']==[] and '不代表整个知识库' in result['notice']
    assert '不再可以显示' not in json.dumps(result)


@pytest.mark.parametrize('change',['archive','version','request'])
def test_recommendations_recheck_after_model_work(rig,monkeypatch,change):
    from types import SimpleNamespace
    r=rig;doc=r.create();req=create(r).json()
    text='持续离线达到10分钟仍未恢复时提交IT工单。'
    monkeypatch.setattr(r.q,'require_semantic',lambda:SimpleNamespace(search=lambda *a,**k:{'results':[{'document_id':doc,'text':text}]}))
    def classify(question,purpose,items):
        assert [i['id'] for i in items]==[doc]
        with r.q.connect() as c:
            if change=='request':
                c.execute("UPDATE access_requests SET status='cancelled' WHERE id=?",(req['id'],))
            else:
                b=r.q.business_read(doc)
                if change=='archive':b['archived']=True
                else:b['version']+=1
                c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b),doc))
        return {doc:text},True
    monkeypatch.setattr('app.access_recommendations.classify',classify)
    response=r.c.get(PATH+'/'+req['id']+'/recommendations',headers=r.h['head'])
    if change=='request':assert response.status_code==409
    else:
        assert response.status_code==200
        assert response.json()['items']==[]
        assert text not in response.text


def test_request_handler_projection_tracks_routing_and_actual_actor(rig):
    r = rig
    doc = r.create()
    pending = create(r).json()
    assert pending['reviewer_scope'] == '研发部主管或管理层'
    assert pending['handled_by'] is None
    approved = decide(r, pending, who='boss', doc=doc).json()
    assert approved['handled_by'] == 'boss'
    assert approved['reviewer_scope'] is None
    assert listing(r, 'prd')[0]['handled_by'] == 'boss'
    assert r.action(doc, 'head', 'revoke_share', username='prd').status_code == 200
    historical = listing(r, 'prd')[0]
    assert historical['handled_by'] == 'boss' and historical['document'] is None
    rejected = decide(r, create(r).json(), action='reject').json()
    assert rejected['handled_by'] == 'head' and rejected['reviewer_scope'] is None
    cancelled = decide(r, create(r).json(), who='prd', action='cancel').json()
    assert cancelled['handled_by'] == 'prd' and cancelled['reviewer_scope'] is None
    # Preserve an honest empty value for older records without a recorded actor.
    with r.q.connect() as c:
        c.execute('UPDATE access_requests SET actor=NULL WHERE id=?', (cancelled['id'],))
    assert next(x for x in listing(r, 'prd') if x['id'] == cancelled['id'])['handled_by'] is None
    assert listing(r, 'otherhead') == [] and listing(r, 'rd') == []


def test_gap_followup_completion_and_revocation(rig):
    r=rig; req=create(r).json()
    gap=decide(r,req,action='needs_content',note='缺少设备报障时限，研发部补充操作说明。').json()
    assert gap['status']=='needs_content' and gap['gap_actor']=='head'
    assert gap['document'] is None and not gap['access_available']
    assert create(r).json()['id']==req['id']
    assert listing(r,'otherhead')==[] and listing(r,'rd')==[]
    assert decide(r,gap,who='prd',action='resolve',note='越权').status_code==403
    assert decide(r,req,action='needs_content',note='过时更新').status_code==409
    updated=decide(r,gap,action='needs_content',note='操作说明已整理，等待发布。').json()
    doc=r.create(status='submitted')
    assert decide(r,updated,action='resolve',doc=doc,note='已补充').status_code==409
    with r.q.connect() as c:
        assert c.execute('SELECT COUNT(*) FROM business_grants').fetchone()[0]==0
        b=r.q.business_read(doc);b['status']='published'
        c.execute('UPDATE business_documents SET body=? WHERE document_id=?',(json.dumps(b),doc))
    assert decide(r,updated,doc=doc).status_code==409
    resolved=decide(r,updated,action='resolve',doc=doc,note='已发布报障说明，请重新提问。').json()
    assert resolved['status']=='resolved' and resolved['access_available']
    mine=listing(r,'prd')[0]
    assert mine['review_note']=='已发布报障说明，请重新提问。' and mine['gap_note']=='操作说明已整理，等待发布。'
    assert mine['handled_by']=='head' and mine['document']['id']==doc
    assert decide(r,resolved,action='resolve',doc=doc,note='重复').status_code==409
    assert r.action(doc,'head','revoke_share',username='prd').status_code==200
    assert listing(r,'prd')[0]['document'] is None and not listing(r,'prd')[0]['access_available']
    with r.q.connect() as c:
        events=c.execute('SELECT action,note FROM access_request_events WHERE request_id=? ORDER BY version',(req['id'],)).fetchall()
        assert [x[0] for x in events]==['create','needs_content','needs_content','resolve']
        assert events[1][1]=='缺少设备报障时限，研发部补充操作说明。'


@pytest.mark.parametrize('action',['needs_content','reject','resolve'])
def test_gap_requires_reason_and_authorized_state(rig,action):
    r=rig;req=create(r).json()
    if action=='resolve':req=decide(r,req,action='needs_content',note='待补充').json()
    for note in ['', '   ']:
        assert decide(r,req,action=action,note=note).status_code==422
    assert decide(r,req,who='otherhead',action=action,note='说明').status_code==404
    assert decide(r,req,who='prd',action=action,note='说明').status_code==403
    assert decide(r,req,action='needs_content',note='说明',doc=r.create()).status_code==422
    assert listing(r,'prd')[0]['version']==req['version']


def test_gap_cancel_reject_and_resolve_guards(rig):
    r=rig;req=create(r).json();doc=r.create()
    assert decide(r,req,action='resolve',doc=doc,note='未核查').status_code==409
    gap=decide(r,req,action='needs_content',note='待补充').json()
    assert decide(r,gap,who='prd',action='cancel').json()['status']=='cancelled'
    req=create(r).json();assert req['id']!=gap['id']
    gap=decide(r,req,action='needs_content',note='待补充').json()
    rejected=decide(r,gap,action='reject',note='用途需要重新确认').json()
    assert rejected['status']=='rejected' and rejected['review_note']=='用途需要重新确认'
    assert rejected['gap_note']=='待补充'


def test_gap_migration_preserves_legacy_records_and_is_repeatable(rig):
    from app.access_requests import install
    r=rig;req=create(r).json()
    with r.q.connect() as c:
        for name in ('review_note','gap_note','gap_actor'):
            c.execute('ALTER TABLE access_requests DROP COLUMN '+name)
        c.execute('ALTER TABLE access_request_events DROP COLUMN note')
        c.execute('DROP INDEX access_request_open')
        before=tuple(c.execute('SELECT * FROM access_requests').fetchone())
        event=tuple(c.execute('SELECT * FROM access_request_events').fetchone())
    for _ in range(2):install(r.q,r.q,lambda:None,None,None,None)
    with r.q.connect() as c:
        assert tuple(c.execute('SELECT * FROM access_requests').fetchone())==before+(None,None,None)
        assert tuple(c.execute('SELECT * FROM access_request_events').fetchone())==event+(None,)

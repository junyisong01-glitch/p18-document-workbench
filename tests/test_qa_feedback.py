"""Opt-in snapshots, real auth and authorization on every read/write."""
import json
import threading
from app.library_api import principal
from test_business_workflow import rig


def services(r, monkeypatch, doc=None, historical=None):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    source = dict(document_id=doc,revision=1,document_name='授权资料',chunk_id='c1',index_token='i1',text='仅有权限人员可见的原文',id='S1') if doc else None
    class Service:
        def __init__(self):
            self.lock=threading.RLock()
            self.tickets={'ticket':dict(question='设备恢复时间是什么？',audit_id='trace-test',
                evidence=[source] if source else [],provenance=[source] if source else [],
                historical=[dict(document_id=historical,revision=1)] if historical else [])}
        def draft(self,*args):
            return dict(status='drafted',question=args[0],default_candidate_ids=[],candidates=[],request_id='draft-test')
        def answer(self,*args):
            return dict(status='answered',answer_status='answered',answer='恢复时间为 09:00。[S1]',
                        provider='本地证据核对',citations=[source] if source else [])
    instances={}
    def current():
        return instances.setdefault(principal.get()['session_digest'],Service())
    monkeypatch.setattr(r.q,'current_rag',current)
    def run(who='rd',answer=False):
        if answer:
            result=r.c.post('/api/rag/answer',headers=r.h[who],json={'ticket':'ticket','consent':True})
        else:
            result=r.c.post('/api/rag/drafts',headers=r.h[who],json={'question':'不存在的工单什么时候转交？'})
        assert result.status_code==200,result.text
        return result.json()['feedback_context_id']
    return run,instances


def submit(r, token, who='rd', **extra):
    return r.c.post('/api/business/feedback',headers=r.h[who],json=dict(context_id=token,category='missing',note='请核对',**extra))


def test_explicit_feedback_and_login_scoped_context(rig,monkeypatch):
    r=rig;run,instances=services(r,monkeypatch)
    token=run()
    assert r.c.get('/api/business/feedback',headers=r.h['boss']).json()==[]
    assert submit(r,token,'qa').status_code==409
    assert submit(r,token,'guest').status_code==403
    assert submit(r,token,question='伪造原问题').status_code==422
    first=submit(r,token).json()
    assert first['snapshot']['answer']=='没找到可靠依据'
    assert first['snapshot']['citations']==[]
    assert first['snapshot']['request_id']=='draft-test'
    assert submit(r,token).json()['id']==first['id']
    assert len(r.c.get('/api/business/feedback',headers=r.h['rd']).json())==1
    for who in ['qa','head','prd']:
        assert r.c.get('/api/business/feedback',headers=r.h[who]).json()==[]
    assert r.c.get('/api/business/feedback',headers=r.h['guest']).status_code==403
    assert len(r.c.get('/api/business/feedback',headers=r.h['boss']).json())==1
    for service in instances.values():
        if token in getattr(service,'feedback_contexts',{}):service.feedback_contexts[token]['at']-=1801
    assert submit(r,token).status_code==409


def test_feedback_rechecks_revocation_before_create_and_on_read(rig,monkeypatch):
    r=rig;doc=r.create(owner='qa',restricted=True)
    assert r.action(doc,'boss','share',username='rd').status_code==200
    run,_=services(r,monkeypatch,doc)
    token=run(answer=True)
    item=submit(r,token).json()
    assert item['snapshot']['citations'][0]['document_id']==doc
    assert item['snapshot']['answer'].startswith('恢复时间')
    assert r.action(doc,'boss','revoke_share',username='rd').status_code==200
    assert submit(r,token).status_code==409
    result=r.c.get('/api/business/feedback',headers=r.h['rd']).json()[0]
    assert result['snapshot'] is None and not result['context_available'] and result['note']==''
    assert doc not in json.dumps(result) and '09:00' not in json.dumps(result)
    # Existing boss access does not grant the reporter access.
    assert r.c.get('/api/business/feedback',headers=r.h['boss']).json()[0]['snapshot']
    assert r.action(doc,'boss','archive').status_code==200
    assert r.c.get('/api/business/feedback',headers=r.h['boss']).json()[0]['snapshot'] is None


def test_historical_sources_and_revision_changes_fail_closed(rig,monkeypatch):
    r=rig;doc=r.create();old=r.create(owner='qa',restricted=True)
    assert r.action(old,'boss','share',username='rd').status_code==200
    run,_=services(r,monkeypatch,doc,old)
    token=run(answer=True);assert submit(r,token).status_code==200
    assert r.action(old,'boss','revoke_share',username='rd').status_code==200
    assert r.c.get('/api/business/feedback',headers=r.h['rd']).json()[0]['snapshot'] is None
    with r.q.connect() as c:
        raw=json.loads(c.execute('SELECT body FROM documents WHERE id=?',(doc,)).fetchone()[0]);raw['revision']=2
        c.execute('UPDATE documents SET body=? WHERE id=?',(json.dumps(raw),doc))
    assert r.c.get('/api/business/feedback',headers=r.h['boss']).json()[0]['snapshot'] is None


def test_maintenance_is_not_a_supervisor_task_and_notes_do_not_leak(rig,monkeypatch):
    r=rig;run,_=services(r,monkeypatch);record=submit(r,run()).json()
    url='/api/business/feedback/'+record['id']
    body=dict(expected=0,status='resolved',cause='missing',note='已联系部门补充资料')
    for who in ['rd','head','otherhead']:
        assert r.c.put(url,headers=r.h[who],json=body).status_code==403
    assert r.c.put(url,headers=r.h['boss'],json={**body,'note':''}).status_code==422
    assert r.c.put(url,headers=r.h['boss'],json={**body,'cause':'unknown'}).status_code==422
    result=r.c.put(url,headers=r.h['boss'],json=body)
    assert result.status_code==200 and result.json()['handling_note']==body['note']
    assert r.c.put(url,headers=r.h['boss'],json=body).status_code==409
    own=r.c.get('/api/business/feedback',headers=r.h['rd']).json()[0]
    assert own['status']=='resolved' and 'handling_note' not in own and body['note'] not in json.dumps(own,ensure_ascii=False)
    with r.q.connect() as c:assert c.execute('SELECT COUNT(*) FROM qa_feedback_events').fetchone()[0]==1
    legacy=r.c.post('/api/business/gaps',headers=r.h['rd'],json={'question':'历史记录保留'}).json()
    assert r.c.get('/api/business/gaps',headers=r.h['head']).json()[0]['id']==legacy['id']
    assert r.c.get('/api/business/gaps',headers=r.h['boss']).status_code==403

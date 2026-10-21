import json
import sqlite3
from contextlib import closing
from copy import deepcopy

import pytest
from app import main, egress
from app.rag import RagError
from test_workbench import client, HEADERS, upload, wait
from test_rag import rig

CHECKS={k:True for k in egress.CHECKS}

def body(doc,category='public_verified'):
    return {'revision':doc['revision'],'fingerprint':egress.fingerprint(doc),'classification':category,'checks':dict(CHECKS)}

def audit(data):
    with closing(sqlite3.connect(data/'workbench.sqlite3')) as c:
        return [(a,json.loads(b)) for a,b in c.execute('select action,body from external_audit order by id')]

@pytest.mark.parametrize('category',['fictional','public_verified'])
def test_grant_and_revoke_real_api(client,category):
    d=wait(client,upload(client)['id']);url=f"/api/documents/{d['id']}/external-permission"
    original=deepcopy(main.get(d['id']))
    assert not d['external_permission']['allowed']
    assert client.post(url,headers=HEADERS,json=body(d,category)).json()['allowed'] is True
    assert egress.allowed(main.DATA,main.get(d['id']))
    assert main.get(d['id'])==original
    assert client.get('/api/documents/'+d['id']).json()['external_permission']['classification']==category
    assert client.post(url+'/revoke',headers=HEADERS,json={'revision':d['revision'],'fingerprint':egress.fingerprint(d)}).json()['allowed'] is False
    assert not egress.allowed(main.DATA,main.get(d['id']))
    records=audit(main.DATA);assert [a for a,b in records]==['permission_granted','permission_revoked']
    for a,b in records:
        assert b['operator']=='local_unauthenticated' and b['checks']==CHECKS and b['revision']==d['revision']
        assert 'reviewer' not in b

@pytest.mark.parametrize('field',list(egress.CHECKS)+['missing','wrong_fingerprint','revision','classification','extra'])
def test_bad_approval_never_grants(client,field):
    d=wait(client,upload(client)['id']);value=body(d)
    if field in CHECKS:value['checks'][field]=False
    elif field=='missing':value['checks'].pop(egress.CHECKS[0])
    elif field=='wrong_fingerprint':value['fingerprint']='0'*64
    elif field=='revision':value['revision']+=1
    elif field=='classification':value['classification']='deidentified'
    else:value['reviewer']='pretend-admin'
    response=client.post(f"/api/documents/{d['id']}/external-permission",headers=HEADERS,json=value)
    assert response.status_code in {409,422}
    assert not egress.allowed(main.DATA,d)

@pytest.mark.parametrize('change',['revision','result','delete','replace'])
def test_version_and_identity_invalidate_permission(client,change):
    d=wait(client,upload(client)['id']);egress.update(main.DATA,d,d['revision'],egress.fingerprint(d),'public_verified',CHECKS)
    changed=deepcopy(d)
    if change=='revision':changed['revision']+=1
    elif change=='result':changed['result']['blocks'][0]['text']='different'
    elif change=='delete':changed['state']='deleted'
    else:changed['id']='new-id'
    assert not egress.allowed(main.DATA,changed)

@pytest.mark.parametrize('state',['review','failed','held'])
def test_approval_does_not_bypass_admission(client,state):
    d=wait(client,upload(client)['id']);d['state']=state;main.save(d)
    response=client.post(f"/api/documents/{d['id']}/external-permission",headers=HEADERS,json=body(d))
    assert response.status_code==409
    assert not egress.allowed(main.DATA,d)

def test_same_origin_guard_unchanged(client):
    d=wait(client,upload(client)['id']);url=f"/api/documents/{d['id']}/external-permission"
    assert client.post(url,json=body(d)).status_code==403
    assert client.post(url,headers={**HEADERS,'Origin':'https://foreign.invalid'},json=body(d)).status_code==403
    assert not egress.allowed(main.DATA,d)

def grant_rig(rig):
    for identifier in ['a','b']:
        d=rig.docs[identifier];d['admission']={'eligible':True}
        egress.update(rig.store.DATA,d,1,egress.fingerprint(d),'public_verified',CHECKS)

def test_public_evidence_real_selection_capture_and_audit(rig):
    grant_rig(rig);draft=rig.rag.draft('负责人是谁？')
    assert all(c['selectable']==(c['evidence']['document_id']!='secret') for c in draft['candidates'])
    p=rig.rag.selection(draft['draft_id'],0,draft['default_candidate_ids']);assert not rig.provider.requests
    result=rig.rag.answer(p['ticket'],True);assert result['status']=='answered'
    sent=json.dumps(rig.provider.requests);assert 'UNAUTHORIZED_PRIVATE' not in sent
    records=audit(rig.store.DATA)
    assert [a for a,b in records][-3:]==['egress_allowed','send_attempt','send_result']
    assert records[-1][1]['code']=='response_received'
    assert records[-1][1]['sources'][0]['classification']=='public_verified'
    assert 'question' not in records[-1][1] and 'answer' not in records[-1][1]

@pytest.mark.parametrize('regrant',[False,True])
def test_pending_ticket_revocation_blocks_even_after_regrant(rig,regrant):
    grant_rig(rig);p=rig.rag.prepare('负责人是谁？');d=rig.docs['b']
    egress.update(rig.store.DATA,d,1,egress.fingerprint(d),revoke=True)
    if regrant:egress.update(rig.store.DATA,d,1,egress.fingerprint(d),'public_verified',CHECKS)
    with pytest.raises(RagError) as e:rig.rag.answer(p['ticket'],True)
    assert e.value.code=='evidence_stale' and not rig.provider.requests
    assert audit(rig.store.DATA)[-1][0]=='egress_blocked'

def test_network_failure_audited_no_retry(rig):
    grant_rig(rig);p=rig.rag.prepare('负责人是谁？')
    def fail(*args):raise RagError('api_timeout','timeout')
    rig.provider.complete=fail
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    records=audit(rig.store.DATA);assert [a for a,b in records][-3:]==['egress_allowed','send_attempt','send_result']
    assert records[-1][1]['code']=='api_timeout'

def test_legacy_grant_is_overridden_by_revocation(rig):
    rig.grant(['b']);d=rig.docs['b'];assert egress.allowed(rig.store.DATA,d)
    egress.update(rig.store.DATA,d,1,egress.fingerprint(d),revoke=True)
    assert not egress.allowed(rig.store.DATA,d)


def test_review_frontend_has_only_requested_fields(client):
    from html.parser import HTMLParser
    class FormInputs(HTMLParser):
        def __init__(self):super().__init__();self.active=False;self.values=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='dialog' and a.get('id')=='external-review-dialog':self.active=True
            if self.active and tag in {'input','textarea'}:self.values.append(a)
        def handle_endtag(self,tag):
            if tag=='dialog':self.active=False
    parser=FormInputs();parser.feed(client.get('/').text)
    assert len(parser.values)==5
    assert sum(a.get('type')=='radio' for a in parser.values)==2
    assert sum(a.get('type')=='checkbox' for a in parser.values)==3
    assert {a.get('value') for a in parser.values if a.get('type')=='radio'}=={'fictional','public_verified'}
    for asset in ['/static/external-permission.js','/static/external-permission.css']:
        assert client.get(asset).status_code==200


def test_audit_write_failure_blocks_model(rig,monkeypatch):
    grant_rig(rig);p=rig.rag.prepare('负责人是谁？')
    def fail(*args):raise sqlite3.OperationalError('offline simulated storage failure')
    monkeypatch.setattr('app.rag.egress_audit',fail)
    with pytest.raises(sqlite3.OperationalError):rig.rag.answer(p['ticket'],True)
    assert not rig.provider.requests


def test_blocked_selection_audits_server_resolved_source(rig,monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(main,'RAG_SERVICE',rig.rag)
    draft=rig.rag.draft('负责人是谁？')
    candidate=next(c for c in draft['candidates'] if c['evidence']['document_id']=='secret')
    with pytest.raises(HTTPException) as exc:
        main.rag_call('selection',draft['draft_id'],0,[candidate['candidate_id']])
    assert exc.value.detail['code']=='selection_forbidden'
    action,details=audit(rig.store.DATA)[-1]
    assert action=='egress_blocked' and details['sources'][0]['document_id']=='secret'
    assert details['sources'][0]['revision']==1 and not rig.provider.requests
    assert 'UNAUTHORIZED_PRIVATE' not in json.dumps(details)

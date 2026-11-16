"""Synthetic keys only. All model HTTP is captured in memory, never sent."""
import json,hashlib
from unittest.mock import patch
import pytest
from app import main
from app.rag import SessionDeepSeekClient,DeepSeekClient,config
from test_library_api import setup
from httpx import URL


def test_personal_keys_are_isolated_and_never_echoed(setup,monkeypatch):
    c,h,_=setup;c.base_url=URL('https://testserver');monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-operator-secret-123')
    assert c.get('/api/rag/credentials',headers=h['rd']).json()['configured']is False
    key='synthetic-personal-secret-123456'
    with patch('app.rag.secure_urlopen',side_effect=AssertionError('must not call model')):
        r=c.put('/api/rag/credentials',headers=h['rd'],json={'api_key':key});assert r.status_code==200 and key not in r.text and r.json()['verified']is False
        assert c.get('/api/rag/credentials',headers=h['rd']).json()['configured']
        assert not c.get('/api/rag/credentials',headers=h['hr']).json()['configured']
    digest=hashlib.sha256(h['rd']['Authorization'][7:].encode()).hexdigest();service=main.MANAGED_RAG[digest];assert service.client.credential()==key
    service.tickets['old-preview']={}
    assert c.delete('/api/rag/credentials',headers=h['rd']).json()['configured']is False
    assert not service.tickets and not service.client.credential()
    assert c.put('/api/rag/credentials',headers=h['rd'],json={'api_key':key}).status_code==200
    assert c.post('/api/library/logout',headers=h['rd']).status_code==200 and digest not in main.MANAGED_RAG
    assert c.get('/api/rag/credentials',headers=h['rd']).status_code==401


def test_credentials_require_auth_https_and_strict_no_echo_input(setup):
    c,h,_=setup
    assert c.put('/api/rag/credentials',json={'api_key':'synthetic-test-key-123'}).status_code==401
    assert c.put('/api/rag/credentials',headers=h['rd'],json={'api_key':'synthetic-test-key-123'}).status_code==400
    c.base_url=URL('https://testserver')
    for body in [{'api_key':'do-not-echo-this invalid value'}, {'api_key':'synthetic-test-key-123','base_url':'https://evil.example'}, {'api_key':['secret-input']}, {'api_key':'x'*3000}]:
        r=c.put('/api/rag/credentials',headers=h['rd'],json=body);assert r.status_code==422 and 'do-not-echo'not in r.text and 'evil.example'not in r.text


def test_session_client_transport_uses_own_key_without_global_mutation(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-other-account-123')
    client=SessionDeepSeekClient();assert not client.configured and DeepSeekClient().configured
    client.set_key('synthetic-own-key-123456');captured=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,n):return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'synthetic result'}}]}).encode()
    def transport(req,timeout):
        captured.append((req.full_url,req.get_header('Authorization'),json.loads(req.data)));return Response()
    with patch('app.rag.secure_urlopen',transport):assert client.complete([{'role':'user','content':'fictional'}],config())=='synthetic result'
    assert captured[0][0]=='https://api.deepseek.com/chat/completions' and captured[0][1]=='Bearer synthetic-own-key-123456'
    assert len(captured)==1


def test_key_cannot_change_during_inflight_request(setup):
    c,h,_=setup;c.base_url=URL('https://testserver');key='synthetic-personal-key-123456'
    assert c.put('/api/rag/credentials',headers=h['rd'],json={'api_key':key}).status_code==200
    digest=hashlib.sha256(h['rd']['Authorization'][7:].encode()).hexdigest();service=main.MANAGED_RAG[digest];service.sessions['synthetic']={'busy':True}
    assert c.delete('/api/rag/credentials',headers=h['rd']).status_code==409
    assert c.put('/api/rag/credentials',headers=h['rd'],json={'api_key':'synthetic-other-key-123456'}).status_code==409
    assert service.client.credential()==key
    service.sessions.clear()


def test_personal_key_cannot_be_forwarded_to_other_host():
    from app.rag import RagError
    client=SessionDeepSeekClient();client.set_key('synthetic-own-key-123456')
    with patch('app.rag.secure_urlopen',side_effect=AssertionError('must not send')):
        with pytest.raises(RagError):client.complete([],{**config(),'base_url':'https://evil.example'})

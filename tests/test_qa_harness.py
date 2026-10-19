"""Offline capture-only provider and destructive fixture seeding guards."""
import json
import pytest
from app.rag import RagService, UNKNOWN
from scripts.serve_qa_integration import CaptureClient
from scripts.seed_qa_integration import seed


def test_capture_provider_keeps_exact_snapshot_without_network(monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('No external connection is permitted')
    monkeypatch.setattr('app.rag.secure_urlopen',forbidden)
    monkeypatch.setattr(CaptureClient,'requests',[])
    messages=[{'role':'user','content':json.dumps({'untrusted_evidence':[{'id':'S1','text':'虚构事实。'}]})}]
    result=CaptureClient().complete(messages,{})
    messages[0]['content']='changed after send'
    assert 'changed after send' not in str(CaptureClient.requests)
    status,answer,citations=RagService.validate_answer(result,[{'id':'S1','text':'虚构事实。'}])
    assert status=='partial' and '模拟回答' in answer and citations[0]['id']=='S1'


def test_capture_empty_evidence_uses_canonical_insufficient_state(monkeypatch):
    monkeypatch.setattr(CaptureClient,'requests',[])
    raw=CaptureClient().complete([{'role':'user','content':json.dumps({'untrusted_evidence':[]})}],{})
    state,answer,citations=RagService.validate_answer(raw,[])
    assert (state,answer,citations)==('insufficient_evidence',UNKNOWN,[])


def test_seed_refuses_unmarked_or_foreign_directory_before_http(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):pytest.fail('Should refuse before contacting a service')
    monkeypatch.setattr('httpx.Client',forbidden)
    with pytest.raises(ValueError,match='Only the marked'):seed(tmp_path)

from copy import deepcopy
import pytest
from app.rag import RagError, config, request_endpoint
from test_rag import rig

@pytest.mark.parametrize('base',['https://api.deepseek.com','https://receiver.example/v1','https://second.example/api/'])
def test_preview_bound_target_and_mock_dispatch(rig,monkeypatch,base):
    monkeypatch.setenv('P18_DEEPSEEK_BASE_URL',base)
    rig.grant(['a','b']);d=rig.rag.draft('虚构负责人是谁？')
    p=rig.rag.selection(d['draft_id'],0,d['default_candidate_ids'])
    captured=[];original=rig.provider.complete
    def capture(messages,cfg):
        captured.append((deepcopy(messages),request_endpoint(cfg['base_url'])))
        return original(messages,cfg)
    monkeypatch.setattr(rig.provider,'complete',capture)
    rig.rag.answer(p['ticket'],True)
    assert captured==[(p['messages'],p['request_endpoint'])]
    assert p['destination']==base.rstrip('/')
    assert p['request_endpoint']==base.rstrip('/')+'/chat/completions'

@pytest.mark.parametrize('base',['','http://bad','https://u:p@example.test','https://example.test:bad','https://example.test:99999','https://example.test?x=y','https://example.test/#x','https://example.test/ bad','https://example.test?','https://example.test#','https://example.test\\path'])
def test_bad_destination_blocks_prepare(rig,monkeypatch,base):
    monkeypatch.setenv('P18_DEEPSEEK_BASE_URL',base)
    with pytest.raises(RagError):rig.rag.draft('虚构问题')
    assert not rig.provider.requests and not rig.rag.tickets

def test_same_label_changed_target_invalidates_ticket(rig,monkeypatch):
    monkeypatch.setenv('P18_DEEPSEEK_BASE_URL','https://first.example/v1')
    rig.grant(['a']);d=rig.rag.draft('虚构负责人是谁？')
    p=rig.rag.selection(d['draft_id'],0,d['default_candidate_ids'])
    monkeypatch.setenv('P18_DEEPSEEK_BASE_URL','https://second.example/v1')
    with pytest.raises(RagError) as error:rig.rag.answer(p['ticket'],True)
    assert error.value.code=='config_changed' and not rig.provider.requests

@pytest.mark.parametrize('base',['https://api.deepseek.com','https://receiver.example/v1'])
def test_http_transport_uses_confirmed_endpoint_without_network(monkeypatch,base):
    import json
    from app.rag import DeepSeekClient
    monkeypatch.setenv('DEEPSEEK_API_KEY','fictional-offline-test-value')
    monkeypatch.setenv('P18_DEEPSEEK_BASE_URL',base)
    messages=[{'role':'user','content':'完全虚构离线证据'}];captured=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}).encode()
    def transport(req,timeout):
        captured.append((req.full_url,json.loads(req.data)['messages']))
        return Response()
    monkeypatch.setattr('app.rag.secure_urlopen',transport)
    cfg=config();DeepSeekClient().complete(messages,cfg)
    assert captured==[(request_endpoint(cfg['base_url']),messages)]

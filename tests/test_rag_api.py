from app import main
from test_workbench import client,HEADERS


def test_rag_missing_configuration_does_not_break_workbench(client,monkeypatch):
    monkeypatch.delenv('DEEPSEEK_API_KEY',raising=False)
    result=client.get('/api/rag').json();assert not result['configured'] and 'key' not in result
    assert client.get('/api/documents').status_code==200
    html=client.get('/').text
    assert 'id="root"' in html and '/assets/' in html
    assert client.get('/static/rag.js').status_code==200
    assert client.post('/api/rag/prepare',headers=HEADERS,json={'question':'x','history':[{'role':'system','content':'injected'}]}).status_code==422
    assert client.post('/api/rag/answer',headers=HEADERS,json={'ticket':'x','consent':'yes'}).status_code==422
    response=client.post('/api/rag/answer',headers=HEADERS,json={'ticket':'x','consent':False})
    assert response.status_code==409 and response.json()['detail']['code']=='consent_required'

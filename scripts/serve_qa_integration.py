"""8772-only harness: real cached local embeddings, capture-only external provider.
Never consults an API key or creates an external inference client.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

class CaptureClient:
    label = '模拟回答 · 未调用外部API'
    configured = True
    requests = []
    def complete(self, messages, cfg):
        self.requests.append(deepcopy(messages))
        payload = json.loads(messages[-1]['content'])
        # Deterministic evidence echo validates the wire path, not model reasoning.
        evidence = payload['untrusted_evidence']
        if not evidence:
            return json.dumps({'status':'insufficient_evidence','answer':'无证据','citations':[]})
        source = evidence[0]
        return json.dumps({'status':'partial','answer':'【模拟回答，仅回显所选证据，不代表真实模型推理】'+source['text']+'['+source['id']+']',
                           'citations':[source['id']]}, ensure_ascii=False)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,required=True);args=parser.parse_args()
    data=args.data_dir.resolve()
    if not data.is_relative_to(Path('/private/tmp')) or not data.name.startswith('p18-qa-8772-'):
        parser.error('Use an explicit new /private/tmp/p18-qa-8772-* directory.')
    if data.exists() and not (data/'.qa-integration-fixture').exists():
        parser.error('Refusing an existing unmarked data directory.')
    with socket.socket() as probe:
        try:probe.bind(('127.0.0.1',8772))
        except OSError:parser.error('8772 is occupied. No running service was changed.')
    data.mkdir(exist_ok=True);(data/'.qa-integration-fixture').touch()
    os.environ.update(P18_DATA_DIR=str(data),P18_SEMANTIC_ENABLED='1',P18_SEARCH_MODE='hybrid_dedup',HF_HUB_OFFLINE='1')
    import app.rag as rag
    rag.DeepSeekClient=CaptureClient
    from app import main as store
    @store.app.get('/api/test-qa-capture')
    def capture():
        return {'simulated_calls':len(CaptureClient.requests),'real_paid_calls':0,'messages':CaptureClient.requests}
    import uvicorn
    uvicorn.run(store.app,host='127.0.0.1',port=8772,workers=1)

if __name__=='__main__':main()

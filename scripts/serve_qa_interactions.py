"""8774-only D preview, fresh data; reuses capture provider, never real API."""
import argparse
import os
from pathlib import Path
import socket
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    args=parser.parse_args();data=args.data_dir.resolve()
    if not data.is_relative_to(Path('/private/tmp')) or not data.name.startswith('p18-qa-8774-'):
        parser.error('Only new /private/tmp/p18-qa-8774-* fixture directories are permitted.')
    if data.exists() and not (data/'.qa-integration-fixture').exists():
        parser.error('Refusing an unmarked existing data directory.')
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:probe.bind(('127.0.0.1',8774))
        except OSError:parser.error('8774 occupied; no process was changed.')
    data.mkdir(exist_ok=True);(data/'.qa-integration-fixture').touch()
    os.environ.update(P18_DATA_DIR=str(data),P18_SEMANTIC_ENABLED='1',P18_SEARCH_MODE='hybrid_dedup',HF_HUB_OFFLINE='1')
    from scripts.serve_qa_integration import CaptureClient
    import app.rag as rag
    def forbidden(*args,**kwargs):raise RuntimeError('External inference is disabled in the 8774 preview.')
    rag.secure_urlopen=forbidden;rag.DeepSeekClient=CaptureClient
    from app import main as store
    @store.app.get('/api/test-qa-capture')
    def capture():
        return {'simulated_calls':len(CaptureClient.requests),'real_paid_calls':0,'messages':CaptureClient.requests,'destinations':CaptureClient.destinations}
    @store.app.get('/api/unified-preview')
    def unified_status():
        import hashlib
        root=Path(__file__).resolve().parents[1]
        files=['web/index.html','web/search.js','web/unified.css','web/qa/live.js','web/qa/live.css','web/qa/flow.js','web/qa/interactions.js','web/qa/sessions.js']
        fingerprint=hashlib.sha256(b''.join((root/name).read_bytes() for name in files)).hexdigest()
        return {'ui_version':'P18-INT-002','port':8774,'data_directory':str(data),
                'provider_mode':'offline_capture','external_requests_enabled':False,'source_fingerprint':fingerprint}
    import uvicorn
    uvicorn.run(store.app,host='127.0.0.1',port=8774,workers=1)


if __name__=='__main__':main()

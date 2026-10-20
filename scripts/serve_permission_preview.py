"""Isolated fictional permission-review preview. Capture model only; no real API."""
import argparse
import os
from pathlib import Path
import socket
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--port',type=int,default=8776)
    a=p.parse_args();data=a.data_dir.resolve()
    if a.port<8776 or not data.is_relative_to(Path('/private/tmp')) or not data.name.startswith('p18-permission-'):
        p.error('Use an isolated port >=8776 and /private/tmp/p18-permission-* directory.')
    if data.exists() and not (data/'.permission-preview').exists():p.error('Refusing an unmarked existing directory.')
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:s.bind(('127.0.0.1',a.port))
        except OSError:p.error('Port occupied; no running process changed.')
    data.mkdir(exist_ok=True);(data/'.permission-preview').touch()
    os.environ.update(P18_DATA_DIR=str(data),P18_SEMANTIC_ENABLED='1',HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    from scripts.serve_qa_integration import CaptureClient
    import app.rag as rag
    def forbidden(*args,**kwargs):raise RuntimeError('Real external requests disabled in permission preview.')
    rag.secure_urlopen=forbidden;rag.DeepSeekClient=CaptureClient
    from app import main as store
    @store.app.get('/api/permission-preview-capture')
    def capture():
        return {'real_paid_calls':0,'simulated_calls':len(CaptureClient.requests),
                'messages':CaptureClient.requests,'destinations':CaptureClient.destinations}
    import uvicorn
    uvicorn.run(store.app,host='127.0.0.1',port=a.port,workers=1)

if __name__=='__main__':main()

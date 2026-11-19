"""Dedicated cloud demo entry, separate from the personal 8896 launcher."""
import os
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def create_app():
    if os.environ.get('P18_CLOUD_DEMO') != '1':
        raise RuntimeError('Public demo must be explicitly enabled')
    if Path(os.environ.get('P18_DATA_DIR', '')).resolve() != ROOT / 'runtime/demo-v1-experience':
        raise RuntimeError('Cloud deployment must use its own packaged runtime')
    if not (ROOT/'CLOUD-DEMO.json').is_file() or json.loads((ROOT/'CLOUD-DEMO.json').read_text()).get('isolated_demo') is not True:
        raise RuntimeError('A sanitized isolated demo bundle is required')
    from deploy.cloud.gateway import DemoGateway
    # Existing wrapper preserves official-only DeepSeek and per-document consent.
    from scripts.experience_server import main
    from app.datasets import install
    return DemoGateway(install(main), origin=os.environ.get('P18_PUBLIC_ORIGIN', ''), enabled=True)


if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()
    import uvicorn
    uvicorn.run(create_app(), host='127.0.0.1', port=int(os.environ.get('P18_CLOUD_PORT', '8896')), workers=1, proxy_headers=False)

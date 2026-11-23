"""Dedicated cloud demo entry, separate from the personal 8896 launcher."""
import os
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def validate_runtime(root):
    marker = root / 'runtime/cloud-demo.json'
    # Legacy packages remain readable; new Git-based deployments use runtime marker.
    if not marker.is_file():
        marker = root / 'CLOUD-DEMO.json'
    if not marker.is_file() or json.loads(marker.read_text()).get('isolated_demo') is not True:
        raise RuntimeError('Import the sanitized data package first; see deploy/cloud/HANDOFF.md')
    for name in ('demo-v1-experience', 'business-workflow'):
        if not (root / 'runtime' / name / 'workbench.sqlite3').is_file():
            raise RuntimeError('Deployment database missing: ' + name)
    if not (root / 'runtime/business-workflow/business-seed.json').is_file():
        raise RuntimeError('Business access seed is missing')


def create_app():
    if os.environ.get('P18_CLOUD_DEMO') != '1':
        raise RuntimeError('Public demo must be explicitly enabled')
    if Path(os.environ.get('P18_DATA_DIR', '')).resolve() != ROOT / 'runtime/demo-v1-experience':
        raise RuntimeError('Cloud deployment must use its own packaged runtime')
    validate_runtime(ROOT)
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

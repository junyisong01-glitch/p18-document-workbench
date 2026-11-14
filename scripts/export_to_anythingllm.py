"""Export the P18 library into AnythingLLM (migration option B, light target).

Same source of truth as export_to_ragflow.py: the P18 SQLite catalogue is read
read-only, originals are kept, and one AnythingLLM workspace is created per
classification. AnythingLLM has no per-document ACL in the desktop edition, so
workspace scope is the coarse substitute and must not be described as
row-level permission.

Dry run is the default. Credentials, sessions and chat history are never read.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.export_to_ragflow import plan


def slug(name):
    safe = ''.join(ch.lower() if ch.isalnum() else '-' for ch in name).strip('-')
    return safe or 'workspace'


class AnythingLLMClient:
    """Minimal REST client for the AnythingLLM server/desktop developer API."""

    def __init__(self, base, api_key, timeout=120):
        self.base = base.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method, path, data=None, content_type='application/json'):
        request = urllib.request.Request(
            f'{self.base}{path}', data=data, method=method,
            headers={'Authorization': f'Bearer {self.api_key}',
                     'Accept': 'application/json',
                     'Content-Type': content_type})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read() or b'{}')
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'AnythingLLM {method} {path} -> {exc.code}: {exc.read()[:300]!r}') from exc

    def workspace(self, name):
        created = self._request('POST', '/api/v1/workspace/new', json.dumps({'name': name}).encode())
        return created['workspace']['slug']

    def upload(self, path):
        boundary = '----p18' + uuid.uuid4().hex
        body = b''.join([
            f'--{boundary}\r\n'.encode(),
            f'Content-Disposition: form-data; name="file"; filename="{Path(path).name}"\r\n'.encode(),
            b'Content-Type: application/octet-stream\r\n\r\n',
            Path(path).read_bytes(),
            f'\r\n--{boundary}--\r\n'.encode(),
        ])
        result = self._request('POST', '/api/v1/document/upload', body,
                               content_type=f'multipart/form-data; boundary={boundary}')
        documents = result.get('documents') or []
        if not documents:
            raise RuntimeError(f'AnythingLLM 未返回文档定位：{result}')
        return documents[0]['location']

    def embed(self, workspace, locations):
        return self._request('POST', f'/api/v1/workspace/{workspace}/update-embeddings',
                             json.dumps({'adds': locations}).encode())


def push(target, workspace, location, client):
    """Create/attach the document to the workspace, then embed it."""
    return client.embed(workspace, [location])


def main(argv=None):
    parser = argparse.ArgumentParser(description='P18 -> AnythingLLM migration export')
    parser.add_argument('--data-dir', default='runtime/demo-v1-experience')
    parser.add_argument('--db', default=None)
    parser.add_argument('--push', action='store_true')
    parser.add_argument('--api-base', default='http://127.0.0.1:3001')
    parser.add_argument('--api-key', default='')
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    db_path = Path(args.db) if args.db else data_dir / 'workbench.sqlite3'
    result = plan(data_dir, db_path)
    groups = {}
    for item in result['items']:
        groups.setdefault(item['dataset'], []).append(item)
    print(json.dumps({'workspaces': {name: len(items) for name, items in groups.items()},
                      'skipped': result['skipped']}, ensure_ascii=False, indent=2))
    if not args.push:
        print('\n dry run：未上传。确认后加 --push 并在 AnythingLLM 里生成 API Key。', file=sys.stderr)
        return 0
    client = AnythingLLMClient(args.api_base, args.api_key)
    for name, items in groups.items():
        workspace = client.workspace(name)
        for item in items:
            push(name, workspace, client.upload(item['path']), client)
    print('uploaded', sum(len(items) for items in groups.values()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

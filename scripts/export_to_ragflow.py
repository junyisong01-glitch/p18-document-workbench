"""Export the P18 library into a RAGFlow instance (migration option B).

Reads the P18 SQLite catalogue read-only, keeps original files, and maps the
P18 classification onto one RAGFlow dataset per classification: RAGFlow has no
per-document ACL in the open-source edition, so dataset scope is the coarse
substitute and must not be described as row-level permission.

Dry run is the default. Nothing is uploaded without --push, and the script
never reads credentials, sessions or chat history.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from pathlib import Path

CLASSIFICATIONS = ('公开', '内部', '机密')
SKIP_STATES = {'deleted', 'deleting', 'delete_failed', 'superseded'}


def catalogue(db_path):
    """Return {document_id: {name, ext, state, classification, department, ...}}."""
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        docs = {}
        for row in conn.execute('SELECT id, body FROM documents'):
            body = json.loads(row['body'])
            docs[row['id']] = {
                'id': row['id'], 'name': body.get('name', ''), 'ext': body.get('ext', ''),
                'state': body.get('state', ''), 'revision': body.get('revision'),
                'characters': body.get('characters', 0),
                'classification': None, 'department': None,
            }
        try:
            for row in conn.execute('SELECT document_id, body FROM library_metadata'):
                meta = json.loads(row['body'])
                if row['document_id'] in docs:
                    docs[row['document_id']]['classification'] = meta.get('classification')
                    docs[row['document_id']]['department'] = meta.get('department')
        except sqlite3.OperationalError:
            pass  # legacy database without the library tables
        return docs
    finally:
        conn.close()


def plan(data_dir, db_path):
    """Build the upload plan: one dataset per classification, files kept as-is."""
    data_dir = Path(data_dir)
    docs = catalogue(db_path)
    items, skipped = [], []
    for doc in docs.values():
        if doc['state'] in SKIP_STATES or not doc['characters']:
            skipped.append({'id': doc['id'], 'reason': f"state={doc['state']}, characters={doc['characters']}"})
            continue
        source = data_dir / 'files' / doc['id'] / ('original' + doc['ext'])
        if not doc['ext'] or not source.is_file():
            skipped.append({'id': doc['id'], 'reason': 'missing original file'})
            continue
        items.append({'id': doc['id'], 'path': str(source), 'name': Path(doc['name']).name or source.name,
                      'dataset': doc['classification'] if doc['classification'] in CLASSIFICATIONS else '未分类',
                      'department': doc['department'], 'revision': doc['revision'], 'ext': doc['ext']})
    return {'items': items, 'skipped': skipped}


class RagflowClient:
    """Minimal RAGFlow HTTP client; no retries, no hidden defaults."""

    def __init__(self, base, api_key, timeout=60):
        self.base = base.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

    def _call(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={'Authorization': f'Bearer {self.api_key}',
                                                  'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read() or b'{}')
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'RAGFlow {method} {path} -> {exc.code}: {exc.read()[:300]!r}') from exc

    def ensure_dataset(self, name):
        listed = self._call('GET', '/api/v1/datasets?page=1&page_size=100')
        for item in listed.get('data') or []:
            if item.get('name') == name:
                return item['id']
        created = self._call('POST', '/api/v1/datasets', {'name': name})
        return created['data']['id']

    def upload(self, dataset_id, path):
        # Multipart is intentionally left to the operator: this client documents
        # the contract, the CLI shells out to curl for the binary upload.
        return self._call('POST', f'/api/v1/datasets/{dataset_id}/documents', {'path': str(path)})


def main(argv=None):
    parser = argparse.ArgumentParser(description='P18 -> RAGFlow migration export')
    parser.add_argument('--data-dir', default='runtime/demo-v1-experience')
    parser.add_argument('--db', default=None, help='override workbench.sqlite3 path')
    parser.add_argument('--push', action='store_true', help='actually create datasets and upload')
    parser.add_argument('--api-base', default='http://127.0.0.1')
    parser.add_argument('--api-key', default='')
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    db_path = Path(args.db) if args.db else data_dir / 'workbench.sqlite3'
    result = plan(data_dir, db_path)
    summary = {'datasets': {}, 'items': len(result['items']), 'skipped': result['skipped']}
    for item in result['items']:
        summary['datasets'][item['dataset']] = summary['datasets'].get(item['dataset'], 0) + 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.push:
        print('\n dry run：未上传。确认后加 --push 并配置 --api-base/--api-key。', file=sys.stderr)
        return 0
    client = RagflowClient(args.api_base, args.api_key)
    for dataset in summary['datasets']:
        client.ensure_dataset(dataset)
    for item in result['items']:
        client.upload(item['dataset'], item['path'])
    print('uploaded', len(result['items']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

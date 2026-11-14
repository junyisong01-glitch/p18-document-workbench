"""Bulk-seed the demo library for scale checks.

Generates synthetic documents with one unique fact each, so retrieval can be
scored by document identity instead of by fuzzy substring. Documents are spread
across classifications and departments, and uploaded with the manager that is
allowed to create them.

    .venv/bin/python scripts/seed_bulk.py --count 120 --workers 4
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from pathlib import Path

BASE = 'http://127.0.0.1:8896'
PASSWORD = 'p18-review-2026'
STAGING = Path('/tmp/p18-bulk')

# (classification, department, owner account, viewers, share)
PLAN = [
    ('公开', '研发部', 'admin', [], 0.35),
    ('内部', '研发部', 'mgr_rd', [], 0.25),
    ('内部', '生产制造部', 'mgr_mfg', [], 0.20),
    ('机密', '研发部', 'mgr_rd', ['启辰研发岗位'], 0.20),
]

_OPENERS = {}
_LOCK = threading.Lock()


def opener_for(username):
    with _LOCK:
        if username in _OPENERS:
            return _OPENERS[username]
        jar = CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        request = urllib.request.Request(
            f'{BASE}/api/library/login',
            data=json.dumps({'username': username, 'password': PASSWORD}).encode(),
            headers={'Content-Type': 'application/json', 'X-P18-Client': 'workbench'}, method='POST')
        opener.open(request, timeout=30).read()
        _OPENERS[username] = opener
        return opener


def call(opener, method, path, payload=None, body=None, content_type='application/json', timeout=120):
    data = body if body is not None else (json.dumps(payload).encode() if payload is not None else None)
    request = urllib.request.Request(f'{BASE}{path}', data=data, method=method,
                                     headers={'Content-Type': content_type, 'X-P18-Client': 'workbench'})
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b'{}')


def multipart(metadata, path, boundary='----p18bulk'):
    body = bytearray()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="metadata_json"\r\n\r\n'
             f'{json.dumps(metadata, ensure_ascii=False)}\r\n').encode()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
             f'filename="{Path(path).name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
    body += Path(path).read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    return bytes(body), f'multipart/form-data; boundary={boundary}'


def build_document(index, classification, department):
    """One document, one unique fact, deterministic wording."""
    from docx import Document
    code = f'BULK-{index:04d}'
    duration = 10 + index % 47
    doc = Document()
    doc.add_heading(f'虚构设备 ZX{index} 维护说明', 0)
    doc.add_heading('1 设备标识', 1)
    doc.add_paragraph(f'本资料完全虚构。设备编号 {code}，归属 {department}，密级 {classification}。')
    doc.add_heading('2 校准参数', 1)
    doc.add_paragraph(f'虚构设备 ZX{index} 的校准时长为 {duration} 分钟，编号 {code}。')
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = '项目'; table.cell(0, 1).text = '数值'
    table.cell(1, 0).text = '校准时长（分钟）'; table.cell(1, 1).text = str(duration)
    path = STAGING / f'{code}.docx'
    doc.save(path)
    return {'index': index, 'code': code, 'duration': duration, 'path': path,
            'classification': classification, 'department': department,
            'name': f'虚构ZX{index}维护说明.docx'}


def wait_ready(opener, identifier, limit=180):
    for _ in range(limit):
        status, doc = call(opener, 'GET', f'/api/documents/{identifier}', timeout=30)
        if status == 200 and doc.get('state') not in {'queued', 'converting', 'parsing'}:
            return doc
        time.sleep(1)
    return None


def accept(opener, identifier, doc):
    keys = [item['key'] for item in (doc.get('admission', {}).get('requirements') or [])]
    if keys:
        call(opener, 'POST', f'/api/documents/{identifier}/review',
             {'action': 'accept', 'revision': doc['revision'], 'reviewer': '虚构批量脚本',
              'checks': {key: True for key in keys}})


def wait_index(opener, identifier, limit=180):
    for _ in range(limit):
        status, payload = call(opener, 'GET', f'/api/documents/{identifier}/index', timeout=30)
        if payload.get('status') in {'complete', 'failed'}:
            return payload.get('status')
        time.sleep(1)
    return 'timeout'


def one(record):
    opener = opener_for(dict(PLAN_BY_KEY)[(record['classification'], record['department'])])
    metadata = {'expected_version': 0, 'code': record['code'], 'name': record['name'],
                'folder': '批量', 'department': record['department'], 'doc_type': '技术文档',
                'classification': record['classification'], 'version': 'V1.0',
                'lifecycle': '现行有效', 'viewers': record['viewers']}
    body, content_type = multipart(metadata, record['path'])
    started = time.time()
    status, result = call(opener, 'POST', '/api/library/upload', body=body,
                          content_type=content_type, timeout=180)
    if status != 200:
        return {**record, 'ok': False, 'status': status}
    identifier = result['id']
    doc = wait_ready(opener, identifier)
    if not doc:
        return {**record, 'ok': False, 'status': 'parse_timeout', 'id': identifier}
    accept(opener, identifier, doc)
    index = wait_index(opener, identifier)
    return {**record, 'ok': index == 'complete', 'status': index, 'id': identifier,
            'elapsed': round(time.time() - started, 1)}


PLAN_BY_KEY = [((classification, department), owner) for classification, department, owner, _, _ in PLAN]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--count', type=int, default=120)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()

    STAGING.mkdir(parents=True, exist_ok=True)
    records = []
    for index in range(1, args.count + 1):
        ratio = (index - 1) / max(1, args.count)
        offset = 0.0
        chosen = PLAN[-1]
        for classification, department, owner, viewers, share in PLAN:
            if ratio < offset + share:
                chosen = (classification, department, owner, viewers, share)
                break
            offset += share
        classification, department, owner, viewers, _ = chosen
        record = build_document(index, classification, department)
        record['owner'] = owner
        record['viewers'] = viewers
        records.append(record)
    print(f'生成 {len(records)} 份文档，开始上传（{args.workers} 并发）', flush=True)

    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for done, item in enumerate(pool.map(one, records), 1):
            results.append(item)
            if done % 20 == 0 or done == len(records):
                ok = sum(1 for r in results if r.get('ok'))
                print(f'  进度 {done}/{len(records)}  成功 {ok}  用时 {round(time.time()-started)}s', flush=True)

    ok = [r for r in results if r.get('ok')]
    report = {'requested': len(records), 'indexed': len(ok),
              'seconds': round(time.time() - started, 1),
              'failures': [{k: r[k] for k in ('code', 'status')} for r in results if not r.get('ok')][:10],
              'documents': [{k: r[k] for k in ('code', 'name', 'classification', 'department',
                                               'duration', 'id', 'owner')} for r in ok]}
    (STAGING / 'bulk-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ('requested', 'indexed', 'seconds')}, ensure_ascii=False))
    return 0 if len(ok) == len(records) else 1


if __name__ == '__main__':
    sys.exit(main())

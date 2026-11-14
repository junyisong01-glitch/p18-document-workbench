"""Scale checks against a seeded library: hit rate, leakage, latency.

Reads /tmp/p18-bulk/bulk-report.json (written by seed_bulk.py) and asks one
unique question per document, as an identity that may read it. Then asks the
same questions as an identity that may NOT read them and asserts the document
never appears in the results.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = 'http://127.0.0.1:8896'
PASSWORD = 'p18-review-2026'
REPORT = Path('/tmp/p18-bulk/bulk-report.json')
OPENERS = {}


def login(username):
    if username in OPENERS:
        return OPENERS[username]
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(
        f'{BASE}/api/library/login',
        data=json.dumps({'username': username, 'password': PASSWORD}).encode(),
        headers={'Content-Type': 'application/json', 'X-P18-Client': 'workbench'}, method='POST')
    opener.open(request, timeout=30).read()
    OPENERS[username] = opener
    return opener


def call(opener, method, path, payload=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(f'{BASE}{path}', data=data, method=method,
                                     headers={'Content-Type': 'application/json',
                                              'X-P18-Client': 'workbench'})
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b'{}')


def ask(opener, question, top_k=5):
    started = time.time()
    status, payload = call(opener, 'POST', '/api/search', {'query': question, 'top_k': top_k})
    elapsed = (time.time() - started) * 1000
    names = [hit['document_name'] for hit in (payload.get('results') or [])]
    return status, names, elapsed


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * fraction))
    return round(ordered[index], 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sample', type=int, default=0, help='0 = 全部')
    parser.add_argument('--leak-sample', type=int, default=25)
    args = parser.parse_args()

    report = json.loads(REPORT.read_text())
    documents = report['documents']
    if args.sample:
        documents = documents[:args.sample]
    print(f'可检索文档 {len(documents)} 份')

    # 1) 命中率：用创建者身份问自己文档的唯一事实
    hits1 = hits5 = 0
    latencies = []
    misses = []
    for doc in documents:
        opener = login(doc['owner'])
        question = f"虚构设备 ZX{doc['code'].split('-')[1].lstrip('0')} 的校准时长是多少"
        status, names, elapsed = ask(opener, question)
        latencies.append(elapsed)
        # search结果里的 document_name 是文件名，不是 library 元数据里的中文名
        expected = f"{doc['code']}.docx"
        if names and names[0] == expected:
            hits1 += 1
        if expected in names[:5]:
            hits5 += 1
        else:
            misses.append({'code': doc['code'], 'question': question, 'got': names[:3]})

    # 2) 越权泄漏：生产岗位问研发/机密文档，文档名不得出现
    leaks = []
    tested = 0
    for doc in documents:
        # 公开资料对所有身份可见；只拿生产岗位本就无权看的资料来测泄漏。
        if doc['classification'] == '公开' or doc['department'] == '生产制造部':
            continue
        if tested >= args.leak_sample:
            break
        tested += 1
        opener = login('prod')
        question = f"虚构设备 ZX{doc['code'].split('-')[1].lstrip('0')} 的校准时长是多少"
        _, names, _ = ask(opener, question)
        if f"{doc['code']}.docx" in names:
            leaks.append({'code': doc['code'], 'got': names})

    # 3) 列表接口耗时（文档数增长后的 N+1 风险）
    admin = login('admin')
    started = time.time()
    status, docs = call(admin, 'GET', '/api/library/documents', timeout=120)
    list_ms = round((time.time() - started) * 1000, 1)

    summary = {
        'documents': len(documents),
        'hit@1': hits1, 'hit@5': hits5,
        'hit@1_rate': round(hits1 / len(documents), 3) if documents else None,
        'hit@5_rate': round(hits5 / len(documents), 3) if documents else None,
        'misses': misses[:10],
        'latency_ms': {'p50': percentile(latencies, 0.5), 'p95': percentile(latencies, 0.95),
                       'max': round(max(latencies), 1) if latencies else None},
        'leak_checked': tested, 'leaks': leaks,
        'list_documents_ms': list_ms, 'list_documents_count': len(docs) if isinstance(docs, list) else None,
        'list_status': status,
    }
    (Path('/tmp/p18-bulk/scale-report.json')).write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({k: summary[k] for k in
                      ('documents', 'hit@1', 'hit@5', 'hit@1_rate', 'hit@5_rate',
                       'latency_ms', 'leak_checked', 'leaks', 'list_documents_ms')},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

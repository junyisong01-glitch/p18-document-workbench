"""Concurrency probe: fixed-workload latency and throughput.

    .venv/bin/python scripts/load_probe.py            # 默认场景
    .venv/bin/python scripts/load_probe.py --base http://127.0.0.1:8896

Every scenario logs in fresh, then fires N requests across C threads and prints
wall time, QPS, p50/p95 and error count. Errors include HTTP 4xx/5xx, so a cold
model or an expired session shows up instead of hiding.
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

SCENARIOS = [
    ('列表 5 并发', '/api/library/documents', None, 5, 10),
    ('列表 20 并发', '/api/library/documents', None, 20, 5),
    ('检索 5 并发', '/api/search', {'query': '虚构设备 ZX5 的校准时长'}, 5, 4),
    ('检索 20 并发', '/api/search', {'query': '校准时长 18 分钟'}, 20, 2),
]


def login(base, username, password):
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.open(urllib.request.Request(
        f'{base}/api/library/login',
        data=json.dumps({'username': username, 'password': password}).encode(),
        headers={'Content-Type': 'application/json', 'X-P18-Client': 'workbench'}, method='POST')).read()
    return opener


def worker(base, opener, path, payload, repeats, out, index):
    times, errors = [], 0
    for _ in range(repeats):
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            base + path, data=data, method='POST' if payload is not None else 'GET',
            headers={'Content-Type': 'application/json', 'X-P18-Client': 'workbench'})
        started = time.time()
        try:
            with opener.open(request, timeout=180) as response:
                response.read()
                times.append((time.time() - started) * 1000)
        except Exception:
            errors += 1
    out[index] = (times, errors)


def run(base, label, path, payload, clients, repeats, username, password):
    opener = login(base, username, password)
    out, started = {}, time.time()
    threads = [threading.Thread(target=worker, args=(base, opener, path, payload, repeats, out, i))
               for i in range(clients)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.time() - started
    times = [value for bucket in out.values() for value in bucket[0]]
    errors = sum(bucket[1] for bucket in out.values())
    total = clients * repeats
    p50 = statistics.median(times) if times else 0
    p95 = sorted(times)[int(len(times) * 0.95) - 1] if times else 0
    print(f'{label:<16} 请求 {total:<3} 墙钟 {wall:5.1f}s  QPS {total / wall:5.1f}  '
          f'p50 {p50:6.0f}ms  p95 {p95:6.0f}ms  错误 {errors}')
    return {'label': label, 'requests': total, 'wall_s': round(wall, 1),
            'qps': round(total / wall, 1), 'p50_ms': round(p50), 'p95_ms': round(p95),
            'errors': errors}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='http://127.0.0.1:8896')
    parser.add_argument('--username', default='dev')
    parser.add_argument('--password', default='p18-review-2026')
    parser.add_argument('--json', default='')
    args = parser.parse_args()
    results = [run(args.base, *scenario, args.username, args.password) for scenario in SCENARIOS]
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as stream:
            json.dump(results, stream, ensure_ascii=False, indent=2)
    return 0 if all(item['errors'] == 0 for item in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())

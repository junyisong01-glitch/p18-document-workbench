"""Retrieval quality probe against a running P18 instance.

Scores by evidence text (substrings) instead of chunk ids, so the same cases
survive a re-parse with a different parser or chunker. Chunk ids change on
every rebuild; facts do not.

Core@k     = at least one expected fact appears inside the top-k results
Complete@k = every expected fact appears inside the top-k results
Unanswerable cases carry no facts; the report only shows how high the best
score still was, which is what a similarity threshold would have to cut.
"""
from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

KS = (1, 3, 5)


def login(base, username, password):
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(
        f'{base}/api/library/login',
        data=json.dumps({'username': username, 'password': password}).encode(),
        headers={'Content-Type': 'application/json', 'X-P18-Client': 'workbench'}, method='POST')
    with opener.open(request, timeout=30) as response:
        if response.status != 200:
            raise SystemExit(f'登录失败: {response.status}')
    return opener


def search(opener, base, query, top_k=5):
    request = urllib.request.Request(
        f'{base}/api/search',
        data=json.dumps({'query': query, 'top_k': top_k}).encode(),
        headers={'Content-Type': 'application/json', 'X-P18-Client': 'workbench'}, method='POST')
    with opener.open(request, timeout=120) as response:
        return json.loads(response.read())


def score(case, results):
    texts = [(item.get('text') or '') for item in results]
    facts = case.get('facts') or []
    rank = None
    for index, text in enumerate(texts, 1):
        if any(fact in text for fact in facts):
            rank = index
            break
    complete = None
    if facts:
        for k in KS:
            if all(any(fact in text for text in texts[:k]) for fact in facts):
                complete = k
                break
    return {'rank': rank, 'complete_at': complete,
            'core': {k: bool(rank and rank <= k) for k in KS},
            'top_score': round(max([item.get('score') or 0 for item in results], default=0), 3)}


def run(opener, base, cases, top_k=5):
    rows = []
    for case in cases:
        result = search(opener, base, case['query'], top_k)
        results = result.get('results') or []
        rows.append({**case, **score(case, results), 'status': result.get('status')})
    return rows


def summarize(rows):
    scored = [row for row in rows if row.get('facts')]
    unanswerable = [row for row in rows if not row.get('facts')]
    summary = {'questions': len(rows), 'scored': len(scored), 'unanswerable': len(unanswerable)}
    for k in KS:
        summary[f'core@{k}'] = sum(1 for row in scored if row['core'][k])
        summary[f'complete@{k}'] = sum(1 for row in scored if row['complete_at'] and row['complete_at'] <= k)
    if unanswerable:
        summary['unanswerable_top_scores'] = [row['top_score'] for row in unanswerable]
    if scored:
        summary['scored_top_scores'] = [row['top_score'] for row in scored]
    return summary


def markdown(rows, summary, corpus_note=''):
    lines = ['| 问题 | 期望事实 | 首次命中 | Top1 分数 |', '|---|---|---|---|']
    for row in rows:
        facts = '、'.join(row.get('facts') or []) or '（无，不可答）'
        hit = f"第 {row['rank']} 条" if row.get('rank') else '未命中'
        lines.append(f"| {row['query']} | {facts} | {hit} | {row['top_score']} |")
    total = summary['scored']
    lines.append('')
    lines.append(f"可答题 {total} 条：Core@1 **{summary['core@1']}/{total}**、"
                 f"Core@3 {summary['core@3']}/{total}、Core@5 {summary['core@5']}/{total}；"
                 f"Complete@1 {summary['complete@1']}/{total}、Complete@3 {summary['complete@3']}/{total}、"
                 f"Complete@5 {summary['complete@5']}/{total}")
    if summary.get('unanswerable_top_scores'):
        lines.append(f"不可答题 {summary['unanswerable']} 条，Top1 分数：{summary['unanswerable_top_scores']}")
    if corpus_note:
        lines.append('')
        lines.append(corpus_note)
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='P18 retrieval quality probe')
    parser.add_argument('--base', default='http://127.0.0.1:8896')
    parser.add_argument('--username', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--cases', required=True)
    parser.add_argument('--top-k', type=int, default=5)
    parser.add_argument('--out', default='')
    args = parser.parse_args(argv)

    cases = json.loads(open(args.cases, encoding='utf-8').read())
    cases = cases['cases'] if isinstance(cases, dict) else cases
    opener = login(args.base, args.username, args.password)
    rows = run(opener, args.base, cases, args.top_k)
    summary = summarize(rows)
    report = markdown(rows, summary)
    print(report)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as stream:
            stream.write(report + '\n')
            stream.write('\n```json\n' + json.dumps(summary, ensure_ascii=False, indent=2) + '\n```\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

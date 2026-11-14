"""End-to-end business-flow checks against a running P18 instance.

Assumes scripts/provision_demo.py and scripts/seed_demo_data.py have run.
Reads and writes only through the public HTTP API, as a browser would.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = 'http://127.0.0.1:8896'
PASSWORD = 'p18-review-2026'
RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, ok, detail))
    print(f"{'✅' if ok else '❌'} {name}{' — ' + detail if detail else ''}")


def login(username):
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(
        f'{BASE}/api/library/login',
        data=json.dumps({'username': username, 'password': PASSWORD}).encode(),
        headers={'Content-Type': 'application/json', 'X-P18-Client': 'workbench'}, method='POST')
    with opener.open(request, timeout=20):
        pass
    return opener


def call(opener, method, path, payload=None, body=None, content_type='application/json'):
    data = body if body is not None else (json.dumps(payload).encode() if payload is not None else None)
    request = urllib.request.Request(f'{BASE}{path}', data=data, method=method,
                                     headers={'Content-Type': content_type, 'X-P18-Client': 'workbench'})
    try:
        with opener.open(request, timeout=120) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b'{}')


def names(opener):
    _, docs = call(opener, 'GET', '/api/library/documents')
    return {doc['name'] for doc in docs}


def main():
    anonymous = urllib.request.build_opener()
    status, _ = call(anonymous, 'GET', '/api/documents')
    check('未登录访问被拒', status == 401, str(status))

    admin, dev, prod = login('admin'), login('dev'), login('prod')

    admin_docs, dev_docs, prod_docs = names(admin), names(dev), names(prod)
    check('管理员看到公开+内部研发', {'虚构ZX8宣传册.docx', '虚构研发规范.docx'} <= admin_docs,
          f'{len(admin_docs)} 份')
    check('研发岗位看到机密资料', '虚构工艺参数.docx' in dev_docs, f'{len(dev_docs)} 份')
    check('管理员看不到未授权的机密', '虚构工艺参数.docx' not in admin_docs)
    check('生产岗位看不到研发内部资料', '虚构研发规范.docx' not in prod_docs, f'{len(prod_docs)} 份')
    check('生产岗位能看本部门内部资料', '虚构产线作业指导.docx' in prod_docs)

    all_docs = {doc['name']: doc for doc in call(admin, 'GET', '/api/library/documents')[1]}
    dev_only = '虚构工艺参数.docx'
    if dev_only in {doc['name'] for doc in call(dev, 'GET', '/api/library/documents')[1]}:
        identifier = next(doc['id'] for doc in call(dev, 'GET', '/api/library/documents')[1]
                          if doc['name'] == dev_only)
        status, _ = call(admin, 'GET', f'/api/documents/{identifier}')
        check('越权按 ID 取文档返回 404', status == 404, str(status))

    status, result = call(dev, 'POST', '/api/search', {'query': '校准多长时间'})
    hits = result.get('results') or []
    check('研发岗位检索命中校准资料', status == 200 and len(hits) > 0,
          f"{len(hits)} 命中，Top1 {round(hits[0]['score'], 3) if hits else '-'}")

    status, result = call(dev, 'POST', '/api/search', {'query': '产线治具点检'})
    names_hit = {hit['document_name'] for hit in (result.get('results') or [])}
    check('检索按权限过滤其他部门资料', 'mfg-guide.docx' not in names_hit, str(sorted(names_hit))[:80])

    status, _ = call(prod, 'POST', '/api/library/upload',
                     body=b'--x\r\n', content_type='multipart/form-data; boundary=x')
    check('非管理员不能上传', status in {403, 422}, str(status))

    status, draft = call(dev, 'POST', '/api/rag/drafts', {'question': '晨间校准几分钟'})
    candidates = draft.get('candidates') or []
    selectable = [c for c in candidates if c['selectable']]
    blocked = [c for c in candidates if not c['selectable']]
    check('RAG 候选生成', status == 200 and candidates, f'{len(candidates)} 候选')
    check('公开资料可外发', any(c['selectable'] for c in candidates), f'{len(selectable)} 可选')
    # Internal material must never be selectable. The reason differs by whether a
    # grant exists: not_authorized (local_only) vs grant + deployment policy.
    check('内部资料不可选',
          all(c['default_reason'] in {'local_only', 'policy_public_only'} for c in blocked),
          str({c['default_reason'] for c in blocked}))

    if selectable:
        payload = {'draft_id': draft['draft_id'], 'selection_version': draft['selection_version'],
                   'candidate_ids': [selectable[0]['candidate_id']]}
        status, selection = call(dev, 'POST', '/api/rag/selection', payload)
        check('选择证据后签发预览票据', status == 200 and selection.get('ticket'), str(status))
        if status == 200:
            status, answer = call(dev, 'POST', '/api/rag/answer',
                                  {'ticket': selection['ticket'], 'consent': True})
            code = (answer.get('detail') or {}).get('code') if isinstance(answer, dict) else None
            check('未配置模型时拒绝发送', status == 409 and code == 'api_not_configured', f'{status} {code}')
            status, again = call(dev, 'POST', '/api/rag/answer',
                                 {'ticket': selection['ticket'], 'consent': True})
            code = (again.get('detail') or {}).get('code') if isinstance(again, dict) else None
            check('票据不可复用', status == 409 and code == 'ticket_expired', f'{status} {code}')

    status, _ = call(dev, 'POST', '/api/gateway/ask', {'question': 'x'})
    check('网关未启用时路由不存在', status == 404, str(status))

    status, _ = call(dev, 'POST', '/api/rag/drafts', {'question': ''})
    check('空问题被拒', status == 422, str(status))

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} 通过")
    if failed:
        print('失败：', '；'.join(failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())

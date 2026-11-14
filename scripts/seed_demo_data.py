"""Seed the demo library with several document groups for end-to-end testing.

Idempotent: re-running skips documents whose content already exists (HTTP 409).
Every document is uploaded as the manager account with explicit classification,
then parsed, reviewed where required, indexed, and (for public material only)
granted the fictional external permission.

Groups:
  public       宣传册.docx / 校准手册.pdf / 设备台账.xlsx
  internal-rd  研发规范.docx           (研发部, 内部)
  internal-mfg 产线作业指导.docx        (生产制造部, 内部)
  confidential 工艺参数.docx            (机密, viewers=启辰研发岗位)
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:8896'

GROUPS = [
    dict(file='brochure.docx', code='PUB-001', name='虚构ZX8宣传册.docx', folder='公开',
         department='研发部', doc_type='技术文档', classification='公开', grant=True),
    dict(file='calibration.pdf', code='PUB-002', name='虚构校准手册.pdf', folder='公开',
         department='研发部', doc_type='技术文档', classification='公开', grant=True),
    dict(file='ledger.xlsx', code='PUB-003', name='虚构设备台账.xlsx', folder='公开',
         department='研发部', doc_type='报表', classification='公开', grant=True),
    dict(file='rd-spec.docx', code='RD-001', name='虚构研发规范.docx', folder='制度',
         department='研发部', doc_type='制度', classification='内部', grant=False),
    dict(file='mfg-guide.docx', code='MFG-001', name='虚构产线作业指导.docx', folder='制度',
         department='生产制造部', doc_type='规程', classification='内部', grant=False,
         owner='mgr_mfg'),
    dict(file='secret.docx', code='SEC-001', name='虚构工艺参数.docx', folder='机密',
         department='研发部', doc_type='规程', classification='机密', grant=False,
         viewers=['启辰研发岗位'], owner='mgr_rd'),
]


def workspace():
    return Path('/tmp/p18-seed')


def build_files(target):
    from docx import Document
    import pymupdf
    from openpyxl import Workbook

    target.mkdir(parents=True, exist_ok=True)
    doc = Document(); doc.add_heading('虚构ZX8宣传册', 0)
    doc.add_paragraph('澄星ZX8是虚构设备，用于演示。校准周期为季度，单次约18分钟。')
    doc.save(target / 'brochure.docx')

    pdf = pymupdf.open(); page = pdf.new_page()
    page.insert_text((48, 72), 'Fictional ZX8 calibration manual.', fontsize=12)
    page.insert_text((48, 96), 'Morning calibration takes 18 minutes; night takes 24.', fontsize=12)
    page.insert_text((48, 120), 'Always verify the fictional power switch first.', fontsize=12)
    pdf.save(target / 'calibration.pdf'); pdf.close()

    book = Workbook(); sheet = book.active; sheet.title = '设备台账'
    sheet.append(['设备编号', '设备名称', '校准时长（分钟）'])
    sheet.append(['ZX8', '虚构澄星ZX8', 18])
    sheet.append(['ZX9', '虚构澄星ZX9', 24])
    book.save(target / 'ledger.xlsx')

    doc = Document(); doc.add_heading('虚构研发规范', 0); doc.add_heading('1 适用范围', 1)
    doc.add_paragraph('本资料完全虚构，仅用于权限演示。')
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = '模式'; table.cell(0, 1).text = '时长'
    table.cell(1, 0).text = '晨间'; table.cell(1, 1).text = '18'
    doc.save(target / 'rd-spec.docx')

    doc = Document(); doc.add_heading('虚构产线作业指导', 0)
    doc.add_paragraph('产线每班点检虚构治具，异常时停机并记录。')
    doc.save(target / 'mfg-guide.docx')

    doc = Document(); doc.add_heading('虚构工艺参数', 0)
    doc.add_paragraph('注塑温度设定为虚构的 218 摄氏度，保压 4 秒。')
    doc.save(target / 'secret.docx')
    return target


def login(username, password):
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    request = urllib.request.Request(
        f'{BASE}/api/library/login',
        data=json.dumps({'username': username, 'password': password}).encode(),
        headers={'Content-Type': 'application/json', 'X-P18-Client': 'workbench'}, method='POST')
    with opener.open(request, timeout=20) as response:
        assert response.status == 200, response.status
    return opener


def multipart(fields, path, boundary='----p18seed'):
    body = bytearray()
    for name, value in fields.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
             f'filename="{Path(path).name}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
    body += Path(path).read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    return bytes(body), f'multipart/form-data; boundary={boundary}'


def call(opener, method, path, payload=None, body=None, content_type='application/json'):
    data = body if body is not None else (json.dumps(payload).encode() if payload is not None else None)
    request = urllib.request.Request(f'{BASE}{path}', data=data, method=method,
                                     headers={'Content-Type': content_type, 'X-P18-Client': 'workbench'})
    try:
        with opener.open(request, timeout=120) as response:
            return response.status, json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b'{}')


def wait_ready(opener, identifier, limit=60):
    for _ in range(limit):
        status, doc = call(opener, 'GET', f'/api/documents/{identifier}')
        if doc.get('state') not in {'queued', 'converting', 'parsing'}:
            return doc
        time.sleep(1)
    raise SystemExit('解析超时')


def accept_review(opener, identifier, doc):
    keys = [item['key'] for item in (doc.get('admission', {}).get('requirements') or [])]
    if not keys:
        return
    call(opener, 'POST', f'/api/documents/{identifier}/review',
         {'action': 'accept', 'revision': doc['revision'], 'reviewer': '虚构种子脚本',
          'checks': {key: True for key in keys}})


def wait_index(opener, identifier, limit=60):
    for _ in range(limit):
        _, status = call(opener, 'GET', f'/api/documents/{identifier}/index')
        if status.get('status') in {'complete', 'failed'}:
            return status
        time.sleep(2)
    return {'status': 'timeout'}


def grant(opener, identifier):
    _, doc = call(opener, 'GET', f'/api/documents/{identifier}')
    permission = doc.get('external_permission') or {}
    return call(opener, 'POST', f'/api/documents/{identifier}/external-permission',
                {'revision': doc['revision'], 'fingerprint': permission.get('fingerprint'),
                 'classification': 'fictional',
                 'checks': {'no_sensitive_content': True, 'third_party_terms_checked': True,
                            'no_restricted_content': True}})


def main():
    target = build_files(workspace())
    openers = {}
    for group in GROUPS:
        owner = group.get('owner', 'admin')
        if owner not in openers:
            openers[owner] = login(owner, 'p18-review-2026')
        opener = openers[owner]
        metadata = {'expected_version': 0, 'code': group['code'], 'name': group['name'],
                    'folder': group['folder'], 'department': group['department'],
                    'doc_type': group['doc_type'], 'classification': group['classification'],
                    'version': 'V1.0', 'lifecycle': '现行有效',
                    'viewers': group.get('viewers', [])}
        body, content_type = multipart({'metadata_json': json.dumps(metadata, ensure_ascii=False)},
                                       target / group['file'])
        status, result = call(opener, 'POST', '/api/library/upload', body=body, content_type=content_type)
        if status == 409:
            print('skip', group['name'], '(内容已存在)')
            continue
        if status != 200:
            print('FAIL', group['name'], status, result); continue
        identifier = result['id']
        doc = wait_ready(opener, identifier)
        accept_review(opener, identifier, doc)
        index = wait_index(opener, identifier)
        if group['grant']:
            grant(opener, identifier)
        print('ok  ', group['name'], '| state', doc.get('state'), '| index', index.get('status'))


if __name__ == '__main__':
    main()

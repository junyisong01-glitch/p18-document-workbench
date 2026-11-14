"""Migration export mapping; no server, no network."""
import json
import sqlite3
from pathlib import Path

from scripts.export_to_ragflow import catalogue, plan


def build_library(root):
    data = root / 'runtime'
    (data / 'files').mkdir(parents=True)
    conn = sqlite3.connect(data / 'workbench.sqlite3')
    conn.execute('CREATE TABLE documents (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    conn.execute('CREATE TABLE library_metadata (document_id TEXT PRIMARY KEY, version INTEGER NOT NULL, body TEXT NOT NULL)')
    rows = [
        ('doc-public', {'name': '公开指南.docx', 'ext': '.docx', 'state': 'ready', 'revision': 1, 'characters': 120}, '公开'),
        ('doc-inner', {'name': '内部规程.pdf', 'ext': '.pdf', 'state': 'ready', 'revision': 2, 'characters': 90}, '内部'),
        ('doc-none', {'name': '未分类.txt', 'ext': '.docx', 'state': 'ready', 'revision': 1, 'characters': 30}, None),
        ('doc-deleted', {'name': '已删.docx', 'ext': '.docx', 'state': 'deleted', 'revision': 1, 'characters': 50}, '公开'),
        ('doc-empty', {'name': '空.docx', 'ext': '.docx', 'state': 'ready', 'revision': 1, 'characters': 0}, '公开'),
        ('doc-missing', {'name': '无原件.docx', 'ext': '.docx', 'state': 'ready', 'revision': 1, 'characters': 40}, '内部'),
    ]
    for identifier, body, classification in rows:
        conn.execute('INSERT INTO documents VALUES (?,?)', (identifier, json.dumps(body, ensure_ascii=False)))
        if classification:
            meta = {'code': identifier, 'name': body['name'], 'folder': '测试', 'department': '研发部',
                    'doc_type': '制度', 'classification': classification, 'version': 'V1',
                    'lifecycle': '现行有效', 'viewers': []}
            conn.execute('INSERT INTO library_metadata VALUES (?,?,?)',
                         (identifier, 1, json.dumps(meta, ensure_ascii=False)))
        if identifier not in {'doc-missing', 'doc-deleted', 'doc-empty'}:
            folder = data / 'files' / identifier
            folder.mkdir(parents=True)
            (folder / ('original' + body['ext'])).write_bytes(b'x')
    conn.commit()
    conn.close()
    return data


def test_plan_groups_by_classification_and_skips_unusable(tmp_path):
    data = build_library(tmp_path)
    result = plan(data, data / 'workbench.sqlite3')
    datasets = sorted(item['dataset'] for item in result['items'])
    assert datasets == ['公开', '内部', '未分类']
    skipped = {item['id'] for item in result['skipped']}
    assert skipped == {'doc-deleted', 'doc-empty', 'doc-missing'}
    assert all(Path(item['path']).is_file() for item in result['items'])


def test_catalogue_never_reads_credentials(tmp_path):
    data = build_library(tmp_path)
    docs = catalogue(data / 'workbench.sqlite3')
    assert 'doc-public' in docs
    flattened = json.dumps(docs, ensure_ascii=False).lower()
    assert 'password' not in flattened and 'salt' not in flattened and 'token' not in flattened

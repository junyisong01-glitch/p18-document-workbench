"""AnythingLLM export mapping; no server, no network."""
import json
import sqlite3
from pathlib import Path

from scripts.export_to_anythingllm import AnythingLLMClient, push, slug
from scripts.export_to_ragflow import plan
from test_ragflow_export import build_library


class FakeClient:
    def __init__(self):
        self.embeds = []

    def embed(self, workspace, locations):
        self.embeds.append((workspace, locations))
        return {'ok': True}


def test_slug_is_url_safe_for_chinese_classification():
    assert slug('公开') != '' and ' ' not in slug('公开') and '/' not in slug('公开')
    assert slug('内部 Docs') == 'docs' or slug('内部 Docs').count('-') >= 1
    assert slug('') == 'workspace'


def test_push_attaches_location_to_workspace():
    client = FakeClient()
    push('公开', 'gong-kai', 'documents/public.docx.json', client)
    assert client.embeds == [('gong-kai', ['documents/public.docx.json'])]


def test_plan_feeds_anythingllm_workspaces(tmp_path):
    data = build_library(tmp_path)
    result = plan(data, data / 'workbench.sqlite3')
    groups = {}
    for item in result['items']:
        groups.setdefault(item['dataset'], []).append(item['path'])
    assert sorted(groups) == ['公开', '内部', '未分类']
    assert all(Path(path).is_file() for paths in groups.values() for path in paths)


def test_client_requires_api_key_shape():
    client = AnythingLLMClient('http://127.0.0.1:3001', 'key')
    assert client.base == 'http://127.0.0.1:3001'
    assert client.api_key == 'key'

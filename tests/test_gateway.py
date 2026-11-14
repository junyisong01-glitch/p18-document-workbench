"""Gateway routing and post-filtering; no network, no live AnythingLLM."""
import pytest
from fastapi import HTTPException

from app import gateway


class Store:
    DATA = '/tmp'

    def __init__(self, docs):
        self._docs = docs

    def all_docs(self):
        return self._docs


class Meta:
    classification = '内部'


class FakeLibraryApi:
    @staticmethod
    def metadata(store, identifier):
        return (1, Meta()) if identifier == 'a' else None


def test_buckets_only_include_classifications_with_visible_docs(monkeypatch):
    store = Store([{'id': 'a', 'name': 'a.docx'}, {'id': 'b', 'name': 'b.docx'}])
    monkeypatch.setattr(gateway, 'visible_documents', lambda s, u: {'a.docx': store._docs[0]})
    monkeypatch.setattr(gateway, 'library_api', FakeLibraryApi)
    assert gateway.buckets_for(store, {}) == ['内部']


def test_answer_drops_sources_the_identity_cannot_read(monkeypatch):
    store = Store([{'id': 'a', 'name': 'a.docx'}])
    monkeypatch.setattr(gateway, 'workspaces', lambda: {'公开': 'slug-public'})
    monkeypatch.setattr(gateway, 'buckets_for', lambda s, u: ['公开'])
    monkeypatch.setattr(gateway, 'visible_documents', lambda s, u: {'a.docx': store._docs[0]})
    monkeypatch.setattr(gateway, '_call', lambda *a, **k: {
        'textResponse': '答案', 'sources': [{'title': 'a.docx', 'score': 0.8},
                                            {'title': 'b.docx', 'score': 0.7}]})
    result = gateway.answer(store, {}, '问题')
    assert result['answer'] == '答案'
    assert [s['title'] for s in result['sources']] == ['a.docx']
    assert result['dropped_sources'] == 1
    assert result['workspaces'] == ['slug-public']


def test_answer_refuses_when_no_workspace_matches(monkeypatch):
    monkeypatch.setattr(gateway, 'workspaces', lambda: {'公开': 'slug-public'})
    monkeypatch.setattr(gateway, 'buckets_for', lambda s, u: ['机密'])
    with pytest.raises(HTTPException) as exc:
        gateway.answer(Store([]), {}, '问题')
    assert exc.value.status_code == 409


def test_ask_body_is_strict():
    with pytest.raises(ValueError):
        gateway.AskBody(question='q', extra='x')
    with pytest.raises(ValueError):
        gateway.AskBody(question='')
    assert gateway.AskBody(question='q').mode == 'query'

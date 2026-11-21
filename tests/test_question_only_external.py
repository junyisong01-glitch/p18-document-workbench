import io
import json
from pathlib import Path

from app import external_model, parser


def test_question_transport_has_no_system_or_retrieved_payload(monkeypatch):
    captured = []

    class MockOpener:
        def open(self, request, timeout):
            captured.append((request.full_url, json.loads(request.data)))
            return io.BytesIO(b'{"choices":[{"finish_reason":"stop","message":{"content":"reference"}}]}')

    monkeypatch.setattr(external_model, 'build_opener', lambda *_: MockOpener())
    question = '公开制度如何办理？'
    assert external_model.question_transport(question, 'offline-testing-key') == 'reference'
    assert captured == [(external_model.ENDPOINT, {
        'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': question}],
        'stream': False, 'max_tokens': 1500, 'thinking': {'type': 'disabled'},
    })]


def test_retired_demo_fixtures_are_readable_by_existing_parsers():
    path = Path(__file__).parent / 'fixtures' / 'demo-library'
    for name in ('虚构ZX8维护指南.docx', '虚构校准记录.xlsx', 'Fictional-Beacon.pdf'):
        file = path / name
        parser.validate(file, file.suffix)
    assert parser.parse_word(path / '虚构ZX8维护指南.docx')['characters'] > 0
    assert parser.parse_pdf(path / 'Fictional-Beacon.pdf')['characters'] > 0

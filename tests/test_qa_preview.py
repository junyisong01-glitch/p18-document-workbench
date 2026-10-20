"""The visual preview must never expose business APIs or files outside web/."""
from pathlib import Path
import importlib.util

spec = importlib.util.spec_from_file_location('qa_preview', Path(__file__).parents[1] / 'scripts/preview_qa.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)

def handler(path='/'):
    instance = object.__new__(preview.PreviewHandler)
    instance.path = path
    return instance

def test_preview_paths_stay_inside_web():
    for path in ['/static/../AGENTS.md', '/../../etc/passwd', '/static/%2e%2e/README.md']:
        assert Path(handler().translate_path(path)) == preview.WEB / '__blocked__'
    assert Path(handler().translate_path('/static/qa/01-home.html')) == preview.WEB / 'qa/01-home.html'

def test_preview_refuses_business_api_and_posts():
    errors = []
    request = handler('/api/rag/answer')
    request.send_error = lambda code, *args: errors.append(code)
    request.do_GET()
    request.do_POST()
    assert errors == [404, 405]

def test_preview_disallows_directory_listing():
    errors = []
    request = handler()
    request.send_error = lambda code, *args: errors.append(code)
    request.list_directory(str(preview.WEB))
    assert errors == [404]

def test_preview_root_opens_mock_mode():
    sent = []
    request = handler()
    request.send_response = lambda code: sent.append(code)
    request.send_header = lambda key, value: sent.append((key, value))
    request.end_headers = lambda: None
    request.do_GET()
    assert sent == [302, ('Location', '/?qa-preview=01')]

import json
import pytest
from scripts import local_llm as launcher

def test_other_provider_never_starts_local_service(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setenv('LLM_PROVIDER', 'deepseek')
    monkeypatch.setattr(launcher, 'tags', lambda: pytest.fail('unexpected health request'))
    launcher.ensure_local_service()

def test_existing_model_is_reused_without_spawning(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setenv('LLM_PROVIDER', 'ollama')
    monkeypatch.setenv('OLLAMA_MODEL', 'installed:test')
    monkeypatch.setattr(launcher, 'tags', lambda: {'models': [{'name': 'installed:test'}]})
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **k: pytest.fail('unexpected spawn'))
    launcher.ensure_local_service()

def test_missing_model_never_downloads_or_replaces_service(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setenv('LLM_PROVIDER', 'ollama')
    monkeypatch.setattr(launcher, 'tags', lambda: {'models': []})
    monkeypatch.setattr(launcher.subprocess, 'Popen', lambda *a, **k: pytest.fail('unexpected spawn'))
    with pytest.raises(RuntimeError, match='不会下载'):
        launcher.ensure_local_service()

def test_owned_start_is_loopback_serial_and_does_not_inherit_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, 'ROOT', tmp_path)
    monkeypatch.setenv('LLM_PROVIDER', 'ollama')
    monkeypatch.setenv('OLLAMA_MODEL', 'installed:test')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'synthetic-not-a-real-key')
    (tmp_path / '.optional/ollama/models').mkdir(parents=True)
    count = iter([None, {'models': [{'name': 'installed:test'}]}])
    def tags():
        value = next(count)
        if value is None: raise OSError('not running')
        return value
    monkeypatch.setattr(launcher, 'tags', tags)
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def connect_ex(self, address): return 1
    monkeypatch.setattr(launcher.socket, 'socket', Socket)
    captured = {}
    class Process:
        pid = 12345
        def poll(self): return None
    def spawn(args, **kwargs):
        captured.update(kwargs); captured['args'] = args
        return Process()
    monkeypatch.setattr(launcher.subprocess, 'Popen', spawn)
    launcher.ensure_local_service()
    env = captured['env']
    assert env['OLLAMA_HOST'] == '127.0.0.1:11434'
    assert env['OLLAMA_NO_CLOUD'] == '1' and env['OLLAMA_NUM_PARALLEL'] == '1'
    assert 'DEEPSEEK_API_KEY' not in env
    assert captured['args'][1:] == ['serve']
    assert json.loads((tmp_path / 'runtime/local-llm/service.json').read_text())['pid'] == 12345

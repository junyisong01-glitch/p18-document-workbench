"""UI-001 entry checks only. No running service, keys, or real model needed."""
from pathlib import Path
import tempfile
import pytest
from scripts import launch_unified_preview as launcher


def test_rejects_unmarked_or_formal_data():
    with pytest.raises(ValueError):launcher.validate_data(Path('/Users/example/runtime'))
    with tempfile.TemporaryDirectory(prefix='p18-qa-8774-',dir='/private/tmp') as directory:
        p=Path(directory)
        with pytest.raises(ValueError):launcher.validate_data(p)
        (p/'.qa-integration-fixture').touch();(p/'workbench.sqlite3').touch()
        assert launcher.validate_data(p)==p.resolve()


@pytest.mark.parametrize('change',['none','real','path','port','old'])
def test_probe_checks_actual_capabilities_and_data(change):
    data=Path('/private/tmp/p18-qa-8774-fictional')
    status={'ui_version':'P18-INT-002','port':8774,'data_directory':str(data),'provider_mode':'offline_capture','external_requests_enabled':False}
    config={'data_directory':str(data)};rag={'provider':'模拟回答 · 未调用外部API'}
    if change=='real':rag['provider']='DeepSeek'
    if change=='path':config['data_directory']='/private/tmp/other'
    if change=='port':status['port']=8765
    if change=='old':status['ui_version']='old'
    fetch=lambda path:{'/api/unified-preview':status,'/api/config':config,'/api/rag':rag}[path]
    assert launcher.probe(data,fetch=fetch)==(change=='none')


def test_occupied_unknown_port_never_spawns_or_stops(monkeypatch):
    monkeypatch.setattr('sys.argv',['launcher','--no-browser'])
    monkeypatch.setattr(launcher,'validate_data',lambda d:Path('/private/tmp/p18-qa-8774-fictional'))
    monkeypatch.setattr(launcher,'occupied',lambda:True);monkeypatch.setattr(launcher,'probe',lambda d:False)
    monkeypatch.setattr(launcher.subprocess,'Popen',lambda *a,**k:pytest.fail('Must not spawn or stop on unknown listener'))
    with pytest.raises(SystemExit):launcher.main()


def test_existing_matching_service_reuses_without_start(monkeypatch):
    monkeypatch.setattr('sys.argv',['launcher'])
    monkeypatch.setattr(launcher,'validate_data',lambda d:Path('/private/tmp/p18-qa-8774-fictional'))
    monkeypatch.setattr(launcher,'occupied',lambda:True);monkeypatch.setattr(launcher,'probe',lambda d:True)
    monkeypatch.setattr(launcher.subprocess,'Popen',lambda *a,**k:pytest.fail('Do not create a duplicate process'))
    opened=[];monkeypatch.setattr(launcher.webbrowser,'open',opened.append)
    launcher.main();assert opened==['http://127.0.0.1:8774']

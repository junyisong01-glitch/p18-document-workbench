import hashlib
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch
import pytest
from scripts import launch


def old_database(data):
    data.mkdir(exist_ok=True)
    (data/'files/doc').mkdir(parents=True)
    (data/'files/doc/original.docx').write_bytes(b'fictional original bytes')
    body={'id':'doc','state':'ready','revision':1,'review_decision':{'reviewer':'fictional reviewer','outcome':'accepted'}}
    with sqlite3.connect(data/'workbench.sqlite3') as conn:
        conn.execute('CREATE TABLE documents (id TEXT PRIMARY KEY, body TEXT)')
        conn.execute('CREATE TABLE events (id INTEGER PRIMARY KEY, action TEXT)')
        conn.execute('INSERT INTO documents VALUES (?,?)',('doc',json.dumps(body)))
        conn.execute("INSERT INTO events VALUES (1,'review_accept')")
    return body


def test_backup_preserves_original_review_and_database(tmp_path):
    body=old_database(tmp_path)
    before=hashlib.sha256((tmp_path/'workbench.sqlite3').read_bytes()).hexdigest()
    backup=launch.backup_before_semantic(tmp_path)
    assert (backup/'files/doc/original.docx').read_bytes()==b'fictional original bytes'
    with sqlite3.connect(backup/'workbench.sqlite3') as c:
        assert json.loads(c.execute('SELECT body FROM documents').fetchone()[0])==body
        assert c.execute('SELECT action FROM events').fetchone()[0]=='review_accept'
    assert hashlib.sha256((tmp_path/'workbench.sqlite3').read_bytes()).hexdigest()==before


def test_legacy_healthy_is_not_semantic_ready(tmp_path):
    with patch.object(launch,'probe',return_value={'config':{'scope':'local'},'semantic':None}),patch.object(launch.subprocess,'Popen') as spawn:
        with pytest.raises(RuntimeError,match='旧版本'):launch.launch(data_dir=tmp_path,semantic=True)
        spawn.assert_not_called()
    assert not (tmp_path/'launcher.json').exists()


def test_existing_disabled_requires_safe_restart(tmp_path):
    reply={'config':{'workbench_version':launch.VERSION,'data_directory':str(tmp_path)},'semantic':{'enabled':False}}
    with patch.object(launch,'probe',return_value=reply),patch.object(launch.subprocess,'Popen') as spawn:
        with pytest.raises(RuntimeError,match='未自动重启'):launch.launch(data_dir=tmp_path,semantic=True)
        spawn.assert_not_called()


def test_existing_other_directory_is_not_reused(tmp_path):
    reply={'config':{'workbench_version':launch.VERSION,'data_directory':str(tmp_path/'other')},'semantic':{'enabled':True}}
    with patch.object(launch,'probe',return_value=reply):
        with pytest.raises(RuntimeError,match='不同的数据目录'):launch.launch(data_dir=tmp_path)


def test_incompatible_database_does_not_get_backed_up_as_valid(tmp_path):
    with sqlite3.connect(tmp_path/'workbench.sqlite3') as conn:conn.execute('CREATE TABLE unrelated(x)')
    with pytest.raises(RuntimeError,match='不兼容'):launch.backup_before_semantic(tmp_path)
    assert not (tmp_path/'backups').exists()


def test_qdrant_directory_lock_detected(tmp_path):
    qdrant=pytest.importorskip('qdrant_client')
    client=qdrant.QdrantClient(path=str(tmp_path/'qdrant'))
    try:
        with pytest.raises(RuntimeError,match='另一个服务'):launch.check_vector_lock(tmp_path)
    finally:client.close()
    launch.check_vector_lock(tmp_path)


def test_missing_model_keeps_document_management_startable(tmp_path):
    root=tmp_path/'mock-project';(root/'.venv/bin').mkdir(parents=True);(root/'.venv/bin/python').touch()
    live={'value':False};reply={'config':{'workbench_version':launch.VERSION,'data_directory':str(tmp_path)},'semantic':{'enabled':False}}
    def probe(url):
        return reply if url.endswith(':8767') and live['value'] else None
    class Process:
        pid=123
        def poll(self):return None
    def spawn(*args,**kwargs):
        assert kwargs['env']['P18_SEMANTIC_ENABLED']=='0'
        live['value']=True
        return Process()
    with patch.object(launch,'ROOT',root),patch.object(launch,'probe',side_effect=probe),patch.object(launch,'check_local_runtime',return_value={'ready':False,'message':'模型缺失'}),patch.object(launch.subprocess,'Popen',side_effect=spawn):
        launch.launch(data_dir=tmp_path,port=8767,semantic=True)
    saved=json.loads((tmp_path/'launcher.json').read_text())
    assert saved['semantic_enabled'] is True and saved['semantic_prepared'] is False

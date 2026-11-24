import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('runtime_bundle', ROOT / 'deploy/cloud/runtime_bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)
spec = importlib.util.spec_from_file_location('cloud_server', ROOT / 'deploy/cloud/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.live = self.root / 'live'
        for name in bundle.DATASETS:
            data = self.live / 'runtime' / name
            data.mkdir(parents=True)
            with sqlite3.connect(data / 'workbench.sqlite3') as c:
                c.executescript('''
                    CREATE TABLE documents(id TEXT PRIMARY KEY,body TEXT);
                    CREATE TABLE library_accounts(username TEXT PRIMARY KEY,salt TEXT,password TEXT,identity TEXT,manager INTEGER,active INTEGER);
                    CREATE TABLE business_profiles(username TEXT PRIMARY KEY,role TEXT,department TEXT,job TEXT,is_demo INTEGER);
                    CREATE TABLE library_sessions(digest TEXT);
                    CREATE TABLE account_invitations(digest TEXT);
                    CREATE TABLE qa_external_settings(enabled INTEGER);
                    CREATE TABLE index_runs(document_id TEXT,body TEXT);
                    CREATE TABLE chunk_runs(document_id TEXT,body TEXT);
                    CREATE TABLE business_events(document_id TEXT,actor TEXT,action TEXT);
                    CREATE TABLE business_grants(document_id TEXT,username TEXT,expires REAL);
                    CREATE TABLE access_requests(id TEXT,question TEXT);
                    CREATE TABLE access_request_events(request_id TEXT,actor TEXT);
                ''')
                c.execute('INSERT INTO documents VALUES (?,?)', ('doc-one', json.dumps({'id': 'doc-one', 'state': 'ready'})))
                c.execute('INSERT INTO documents VALUES (?,?)', ('deleted-one', json.dumps({'id': 'deleted-one', 'state': 'deleted'})))
                for user in bundle.USERS + ('private-user',):
                    c.execute('INSERT INTO library_accounts VALUES (?,?,?,?,?,?)', (user, 'old-salt', 'old-hash', 'identity', 0, 1))
                    c.execute('INSERT INTO business_profiles VALUES (?,?,?,?,?)', (user, 'employee', '研发部', '', 0))
                c.execute("INSERT INTO library_sessions VALUES ('private-session')")
                c.execute("INSERT INTO access_requests VALUES ('private-request','private-question')")
                c.execute("INSERT INTO access_request_events VALUES ('private-request','private-user')")
                c.execute("INSERT INTO account_invitations VALUES ('private-invite')")
                c.execute('INSERT INTO qa_external_settings VALUES (1)')
                c.execute('INSERT INTO index_runs VALUES (?,?)', ('doc-one', '{"status":"complete"}'))
                c.execute("INSERT INTO business_events VALUES ('doc-one','demo_manager','approved')")
                c.execute("INSERT INTO business_grants VALUES ('doc-one','qichen_prd',NULL)")
                c.execute("INSERT INTO business_grants VALUES ('doc-one','private-user',NULL)")
            folder = data / 'files/doc-one'
            folder.mkdir(parents=True)
            (folder / 'original.txt').write_text('fictional document')
            (data / 'business-seed.json').write_text('{"acl":{"doc-one":["研发部"]}}')
            (data / 'private-login.txt').write_text('do not export')
        self.archive = self.root / 'handoff.tar.gz'

    def export(self):
        return bundle.export_runtime(self.live, self.archive)

    def test_roundtrip_preserves_business_and_clears_credentials(self):
        source = self.live / 'runtime/demo-v1-experience/workbench.sqlite3'
        before = source.read_bytes()
        result = self.export()
        destination = self.root / 'target/runtime'
        marker = bundle.import_runtime(self.archive, destination, result['sha256'])
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(marker['documents']['business-workflow'], 2)
        self.assertTrue(marker['indexes_rebuild_required'])
        server.validate_runtime(destination.parent)
        with sqlite3.connect(destination / 'demo-v1-experience/workbench.sqlite3') as c:
            self.assertEqual(c.execute('SELECT count(*) FROM library_accounts').fetchone()[0], 14)
            self.assertEqual(c.execute("SELECT count(*) FROM library_accounts WHERE password='old-hash'").fetchone()[0], 0)
            for name in bundle.CLEAR & bundle.tables(c):
                self.assertEqual(c.execute('SELECT count(*) FROM ' + name).fetchone()[0], 0)
        with sqlite3.connect(destination / 'business-workflow/workbench.sqlite3') as c:
            self.assertEqual(c.execute('SELECT count(*) FROM documents').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT count(*) FROM business_events').fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT username FROM business_grants').fetchall(), [('qichen_prd',)])
        self.assertFalse((destination / 'demo-v1-experience/private-login.txt').exists())
        self.assertEqual((destination / 'business-workflow/files/doc-one/original.txt').read_text(), 'fictional document')
        with self.assertRaises(ValueError):
            bundle.import_runtime(self.archive, destination, result['sha256'])
        with self.assertRaises(ValueError):
            self.export()

    def test_wrong_checksum_and_traversal_do_not_create_runtime(self):
        self.export()
        destination = self.root / 'target/runtime'
        with self.assertRaises(ValueError):
            bundle.import_runtime(self.archive, destination, '0' * 64)
        bad = self.root / 'bad.tar.gz'
        with tarfile.open(bad, 'w:gz') as tar:
            member = tarfile.TarInfo('../escape'); member.size = 1
            tar.addfile(member, io.BytesIO(b'x'))
        with self.assertRaises(ValueError):
            bundle.import_runtime(bad, destination, bundle.sha(bad))
        self.assertFalse(destination.exists())
        self.assertFalse((self.root / 'escape').exists())

    def test_new_tables_are_not_silently_exported(self):
        with sqlite3.connect(self.live / 'runtime/business-workflow/workbench.sqlite3') as c:
            c.execute('CREATE TABLE private_tokens(value TEXT)')
        with self.assertRaisesRegex(ValueError, 'new tables'):
            self.export()
        self.assertFalse(self.archive.exists())

    def test_busy_or_missing_original_stops_export(self):
        db = self.live / 'runtime/business-workflow/workbench.sqlite3'
        with sqlite3.connect(db) as c:
            c.execute('UPDATE documents SET body=? WHERE id=?', ('{"state":"parsing"}', 'doc-one'))
        with self.assertRaisesRegex(ValueError, 'Processing'):
            self.export()
        with sqlite3.connect(db) as c:
            c.execute('UPDATE documents SET body=? WHERE id=?', ('{"state":"ready"}', 'doc-one'))
        (self.live / 'runtime/business-workflow/files/doc-one/original.txt').unlink()
        (self.live / 'runtime/business-workflow/files/doc-one').rmdir()
        with self.assertRaisesRegex(ValueError, 'Original folder'):
            self.export()

    def test_startup_rejects_marker_without_databases(self):
        with self.assertRaises(RuntimeError):
            server.validate_runtime(self.root)
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime/cloud-demo.json').write_text('{"isolated_demo":true}')
        with self.assertRaisesRegex(RuntimeError, 'database missing'):
            server.validate_runtime(self.root)


if __name__ == '__main__':
    unittest.main()

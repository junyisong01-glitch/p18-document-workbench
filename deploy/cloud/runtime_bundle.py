"""Portable demo data handoff; no local credentials, sessions or model weights.

The package is a separate transfer artifact, never a Git-tracked source file.
Only imports into a new runtime directory; existing deployments are not replaced.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import secrets
import shutil
import sqlite3
import tarfile
import tempfile

DATASETS = ('demo-v1-experience', 'business-workflow')
USERS = ('demo_manager', 'qichen_rd_head', 'qichen_prd_head', 'qichen_fin_head',
         'qichen_hr_head', 'qichen_adm_head', 'qichen_rd', 'qichen_qa', 'qichen_ops',
         'qichen_prd', 'qichen_fin', 'qichen_hr', 'qichen_adm', 'qichen_guest')
KEEP = {'library_settings', 'library_metadata', 'library_catalog', 'library_folder_creators',
        'library_accounts', 'business_profiles', 'documents', 'events', 'chunk_runs', 'chunks',
        'business_documents', 'business_events', 'business_grants', 'business_edits'}
CLEAR = {'library_sessions', 'library_login_attempts', 'account_invitations',
         'external_permissions', 'external_audit', 'business_role_audit',
         'qa_external_settings', 'qa_external_audit', 'knowledge_gaps',
         'knowledge_gap_reporters', 'knowledge_gap_events', 'qa_feedback',
         'qa_feedback_events', 'index_runs'}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_db(path):
    return sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)


def tables(conn):
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def validate_idle(conn):
    if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Database integrity check failed')
    for table, field, active in [('documents', 'state', {'queued', 'parsing', 'converting', 'deleting'}),
                                 ('chunk_runs', 'status', {'queued', 'running', 'building'}),
                                 ('index_runs', 'status', {'queued', 'running', 'building'})]:
        if table in tables(conn):
            for (body,) in conn.execute('SELECT body FROM ' + table):
                if json.loads(body).get(field) in active:
                    raise ValueError('Processing still active; wait or stop the service before exporting')


def business_fingerprint(conn):
    # Ignore transient sessions/login attempts but detect changes to retained business state.
    return {name: sorted(conn.execute('SELECT * FROM "' + name + '"').fetchall(), key=repr)
            for name in tables(conn) & KEEP}


def clean_database(path, central):
    with sqlite3.connect(path) as conn:
        names = tables(conn)
        if names - KEEP - CLEAR:
            raise ValueError('Review new tables before export: ' + ', '.join(sorted(names - KEEP - CLEAR)))
        conn.execute('PRAGMA secure_delete=ON')
        for table in names & CLEAR:
            conn.execute('DELETE FROM "' + table + '"')
        marks = ','.join('?' for _ in USERS)
        if central:
            for table in ('library_accounts', 'business_profiles'):
                conn.execute('DELETE FROM ' + table + ' WHERE username NOT IN (' + marks + ')', USERS)
            if conn.execute('SELECT count(*) FROM library_accounts').fetchone()[0] != len(USERS):
                raise ValueError('Expected all 14 demo accounts')
            if conn.execute('SELECT count(*) FROM business_profiles').fetchone()[0] != len(USERS):
                raise ValueError('Expected all 14 demo profiles')
            for username in USERS:
                salt = secrets.token_hex(16)
                password = hashlib.scrypt(secrets.token_bytes(48), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
                conn.execute('UPDATE library_accounts SET salt=?,password=?,active=1 WHERE username=?', (salt, password, username))
            conn.execute('UPDATE business_profiles SET is_demo=1')
        else:
            conn.execute('DELETE FROM library_accounts')
            if 'business_profiles' in names:
                conn.execute('DELETE FROM business_profiles')
        if 'business_grants' in names:
            conn.execute('DELETE FROM business_grants WHERE username NOT IN (' + marks + ')', USERS)
        conn.commit()
        conn.execute('VACUUM')


def export_runtime(live, output):
    if not hasattr(hashlib, 'scrypt'):
        raise RuntimeError('Use Python 3.12 with OpenSSL/scrypt support for export')
    live, output = live.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(live / 'runtime'):
        raise ValueError('Use a new output path outside the source runtime')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='p18-handoff-', dir=output.parent) as work:
        root = Path(work)
        runtime = root / 'runtime'
        counts = {}
        for name in DATASETS:
            source = live / 'runtime' / name
            target = runtime / name
            target.mkdir(parents=True)
            with read_db(source / 'workbench.sqlite3') as old:
                validate_idle(old)
                before = old.execute('SELECT id, body FROM documents ORDER BY id').fetchall()
                retained_before = business_fingerprint(old)
                with sqlite3.connect(target / 'workbench.sqlite3') as new:
                    old.backup(new)
            clean_database(target / 'workbench.sqlite3', name == DATASETS[0])
            (target / 'files').mkdir()
            for identifier, body in before:
                if not identifier or PurePosixPath(identifier).name != identifier or identifier in {'.', '..'}:
                    raise ValueError('Invalid document ID')
                folder = source / 'files' / identifier
                if not folder.exists():
                    if json.loads(body).get('state') != 'deleted':
                        raise ValueError('Original folder missing for active document: ' + identifier)
                    continue  # Retain deleted-record history without inventing an original.
                if folder.is_symlink() or any(p.is_symlink() for p in folder.rglob('*')):
                    raise ValueError('Symlinks are not allowed in document folders')
                hashes = {str(p.relative_to(folder)): sha(p) for p in folder.rglob('*') if p.is_file()}
                shutil.copytree(folder, target / 'files' / identifier)
                for relative, digest in hashes.items():
                    if sha(folder / relative) != digest or sha(target / 'files' / identifier / relative) != digest:
                        raise ValueError('Source file changed during export; retry while idle')
            with read_db(source / 'workbench.sqlite3') as old:
                validate_idle(old)
                if retained_before != business_fingerprint(old):
                    raise ValueError('Documents changed during export; retry while idle')
            counts[name] = len(before)
            if name == 'business-workflow':
                seed = json.loads((source / 'business-seed.json').read_text())
                ids = {row[0] for row in before}
                (target / 'business-seed.json').write_text(json.dumps({'acl': {k: v for k, v in seed['acl'].items() if k in ids}}, ensure_ascii=False))
            else:
                (target / 'business-demo-enabled.json').write_text('{"enabled":true}')
        marker = {'isolated_demo': True, 'schema': 1, 'accounts': len(USERS), 'documents': counts,
                  'sessions_exported': False, 'passwords_rotated': True, 'personal_keys_exported': False,
                  'weights_included': False, 'indexes_rebuild_required': True, 'demo_offline': True}
        (runtime / 'cloud-demo.json').write_text(json.dumps(marker, ensure_ascii=False, indent=2))
        files = {str(p.relative_to(root)): sha(p) for p in runtime.rglob('*') if p.is_file()}
        (root / 'MANIFEST.json').write_text(json.dumps({'schema': 1, 'files': files}, ensure_ascii=False, indent=2))
        # Exclusive create: never replace a previous handoff package.
        created = False
        try:
            with output.open('xb') as stream:
                created = True
                with tarfile.open(fileobj=stream, mode='w:gz') as archive:
                    for p in sorted(root.rglob('*')):
                        if p.is_file():
                            archive.add(p, arcname=str(p.relative_to(root)), recursive=False)
        except BaseException:
            if created:
                output.unlink(missing_ok=True)
            raise
    output.chmod(0o600)
    digest = sha(output)
    output.with_name(output.name + '.sha256').write_text(digest + '  ' + output.name + '\n')
    return {'archive': str(output), 'sha256': digest, 'documents': counts, 'accounts': len(USERS)}


def unpack_verified(archive_path, target, expected_sha):
    if sha(archive_path) != expected_sha:
        raise ValueError('Archive SHA256 mismatch')
    with tarfile.open(archive_path, 'r:gz') as archive:
        members = archive.getmembers()
        names = set()
        if len(members) > 200000 or sum(m.size for m in members) > 20 * 1024**3:
            raise ValueError('Archive exceeds handoff limits')
        for m in members:
            path = PurePosixPath(m.name)
            if (not m.isfile() or path.is_absolute() or '..' in path.parts or '\\' in m.name
                    or m.name in names or not (m.name == 'MANIFEST.json' or path.parts[0] == 'runtime')):
                raise ValueError('Unsafe archive member')
            names.add(m.name)
        for m in members:
            destination = target / m.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(m) as src, destination.open('xb') as dst:
                shutil.copyfileobj(src, dst)
    manifest = json.loads((target / 'MANIFEST.json').read_text())
    if manifest.get('schema') != 1 or set(manifest['files']) != names - {'MANIFEST.json'}:
        raise ValueError('Manifest inventory mismatch')
    for name, digest in manifest['files'].items():
        if sha(target / name) != digest:
            raise ValueError('File hash mismatch: ' + name)
    runtime = target / 'runtime'
    marker = json.loads((runtime / 'cloud-demo.json').read_text())
    if marker.get('isolated_demo') is not True or marker.get('schema') != 1:
        raise ValueError('Not an isolated demo package')
    for name in DATASETS:
        with read_db(runtime / name / 'workbench.sqlite3') as conn:
            validate_idle(conn)
            for table in tables(conn) & CLEAR:
                if conn.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0]:
                    raise ValueError('Package contains sessions, external settings or stale indexes')
    return marker


def import_runtime(archive_path, destination, expected_sha):
    destination = destination.resolve()
    if destination.exists():
        raise ValueError('Destination runtime already exists; never overwrite a running deployment')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.p18-import-', dir=destination.parent) as work:
        marker = unpack_verified(archive_path.resolve(), Path(work), expected_sha)
        if destination.exists():
            raise ValueError('Destination appeared during import')
        (Path(work) / 'runtime').rename(destination)
    return marker


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('export'); p.add_argument('--live', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('import'); p.add_argument('--archive', type=Path, required=True); p.add_argument('--runtime', type=Path, required=True); p.add_argument('--sha256', required=True)
    args = parser.parse_args()
    result = export_runtime(args.live, args.output) if args.command == 'export' else import_runtime(args.archive, args.runtime, args.sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))

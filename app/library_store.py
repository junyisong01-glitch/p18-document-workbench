"""Persistent library metadata and server-issued local test sessions.

Session issuance is a trusted local operation, never an HTTP identity switch.
"""
from dataclasses import asdict
import hashlib
import json
import os
import secrets
import time
from app.library_policy import IDENTITIES, LibraryMetadata


def initialize(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS library_settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS library_metadata (document_id TEXT PRIMARY KEY, version INTEGER NOT NULL, body TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS library_sessions (digest TEXT PRIMARY KEY, identity TEXT NOT NULL, manager INTEGER NOT NULL, expires REAL NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS library_catalog (kind TEXT NOT NULL, name TEXT NOT NULL, PRIMARY KEY(kind,name))')
    conn.execute('CREATE TABLE IF NOT EXISTS library_folder_creators (name TEXT NOT NULL, identity TEXT NOT NULL, PRIMARY KEY(name,identity))')
    initialize_accounts(conn)
    if "demo" not in {r[1] for r in conn.execute("PRAGMA table_info(library_sessions)")}:
        conn.execute("ALTER TABLE library_sessions ADD COLUMN demo INTEGER NOT NULL DEFAULT 0")


def initialize_accounts(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS library_accounts (username TEXT PRIMARY KEY, salt TEXT NOT NULL, password TEXT NOT NULL, identity TEXT NOT NULL, manager INTEGER NOT NULL, active INTEGER NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS library_login_attempts (username TEXT PRIMARY KEY, failures INTEGER NOT NULL, until REAL NOT NULL)')
    if 'username' not in {r[1] for r in conn.execute('PRAGMA table_info(library_sessions)')}:
        conn.execute('ALTER TABLE library_sessions ADD COLUMN username TEXT')


def demo_enabled(conn):
    return (os.environ.get('P18_LIBRARY_DEMO') == '1' and enabled(conn)
            and conn.execute("SELECT 1 FROM library_settings WHERE name='demo' AND value='1'").fetchone() is not None)


def enabled(conn):
    return conn.execute("SELECT 1 FROM library_settings WHERE name='enabled' AND value='1'").fetchone() is not None


def enable(conn):
    conn.execute("INSERT OR REPLACE INTO library_settings VALUES ('enabled','1')")


def issue_session(conn, identity, *, manager=False, lifetime=3600):
    if identity not in IDENTITIES or not 1 <= lifetime <= 86400:
        raise ValueError('身份或会话有效期无效')
    token = secrets.token_urlsafe(32)
    conn.execute('INSERT INTO library_sessions (digest,identity,manager,expires) VALUES (?,?,?,?)',
                 (hashlib.sha256(token.encode()).hexdigest(), identity, int(manager), time.time()+lifetime))
    return token


def resolve_session(conn, token):
    return session_by_digest(conn, hashlib.sha256(token.encode()).hexdigest())


def read(conn, document_id):
    row = conn.execute('SELECT version,body FROM library_metadata WHERE document_id=?', (document_id,)).fetchone()
    if not row:
        return None
    body = json.loads(row[1])
    body['viewers'] = tuple(body['viewers'])
    return row[0], LibraryMetadata(**body)


def write(conn, document_id, metadata, expected_version):
    body = json.dumps(asdict(metadata), ensure_ascii=False)
    if expected_version == 0:
        cursor = conn.execute('INSERT OR IGNORE INTO library_metadata VALUES (?,1,?)', (document_id, body))
    else:
        cursor = conn.execute('UPDATE library_metadata SET version=version+1,body=? WHERE document_id=? AND version=?',
                              (body, document_id, expected_version))
    if cursor.rowcount != 1:
        raise ValueError('文档分类已变化，请刷新后重试')
    return expected_version + 1


def create_account(conn, username, password, identity, *, manager=False):
    """Trusted local provisioning only. Passwords never leave this function."""
    if identity not in IDENTITIES or not username.strip() or len(username) > 100 or not 12 <= len(password) <= 1024:
        raise ValueError('账号、身份或密码不符合要求（密码至少12字符）')
    salt = secrets.token_hex(16)
    hashed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    conn.execute('INSERT INTO library_accounts VALUES (?,?,?,?,?,?)', (username, salt, hashed, identity, int(manager), 1))


def login(conn, username, password):
    import hmac
    row = conn.execute('SELECT salt,password,identity,manager,active FROM library_accounts WHERE username=?', (username,)).fetchone()
    # Same password work for unknown users; throttle failures per account name.
    attempt = conn.execute('SELECT failures,until FROM library_login_attempts WHERE username=?', (username,)).fetchone()
    if attempt and attempt[0] >= 5 and attempt[1] > time.time():
        return None
    salt = row[0] if row else '00'*16
    hashed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    if not row or not row[4] or not hmac.compare_digest(hashed, row[1]):
        failures = attempt[0]+1 if attempt and attempt[1] > time.time() else 1
        conn.execute('INSERT OR REPLACE INTO library_login_attempts VALUES (?,?,?)', (username, failures, time.time()+300))
        return None
    conn.execute('DELETE FROM library_login_attempts WHERE username=?', (username,))
    token = issue_session(conn, row[2], manager=bool(row[3]))
    conn.execute('UPDATE library_sessions SET username=? WHERE digest=?', (username, hashlib.sha256(token.encode()).hexdigest()))
    return token


def revoke_session(conn, token):
    conn.execute('DELETE FROM library_sessions WHERE digest=?', (hashlib.sha256(token.encode()).hexdigest(),))


def session_by_digest(conn, digest):
    row = conn.execute('SELECT identity,manager,expires,username,demo FROM library_sessions WHERE digest=? AND expires>?', (digest, time.time())).fetchone()
    if not row or row[0] not in IDENTITIES or (row[4] and not demo_enabled(conn)):
        return None
    if row[3]:
        account = conn.execute('SELECT identity,manager,active FROM library_accounts WHERE username=?', (row[3],)).fetchone()
        if not account or not account[2] or account[0] != row[0] or bool(account[1]) != bool(row[1]):
            return None
    from app.business_roles import profile
    extra=profile(conn,row[3]) if row[3] else None
    return {'demo':bool(row[4]), 'identity':row[0], 'manager':bool(row[1]), 'session_digest':digest,
            'expires':row[2], 'username':row[3] or '', **(extra or {})}

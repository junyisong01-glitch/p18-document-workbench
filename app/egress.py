"""Local, unauthenticated human egress approval. Never verifies public provenance."""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid

from app.chunking import digest

CHECKS = ('no_sensitive_content', 'third_party_terms_checked', 'no_restricted_content')
CLASSES = {'fictional', 'public_verified'}


def fingerprint(doc):
    return digest({'id':doc['id'],'revision':doc['revision'],'sha256':doc.get('sha256'),'result':doc.get('result')})


def connect(data):
    c = sqlite3.connect(Path(data)/'workbench.sqlite3', timeout=15)
    c.execute('CREATE TABLE IF NOT EXISTS external_permissions (document_id TEXT PRIMARY KEY, body TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS external_audit (id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, body TEXT NOT NULL)')
    return c


def record(data, doc):
    """New records (including revocations) override legacy operator JSON grants."""
    db = Path(data)/'workbench.sqlite3'
    if db.exists():
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True)) as c:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name='external_permissions'").fetchone():
                row = c.execute('SELECT body FROM external_permissions WHERE document_id=?',(doc['id'],)).fetchone()
                if row:return json.loads(row[0])
    try:return json.loads((Path(data)/'rag-permissions.json').read_text()).get(doc['id'],{})
    except (OSError,ValueError,TypeError,AttributeError):return {}


def allowed(data, doc):
    try:
        g=record(data,doc)
        new=g.get('mechanism')=='local_human_confirmation'
        classification_ok=(g.get('classification') in CLASSES and all(g.get('checks',{}).get(k) is True for k in CHECKS)) if new else (g.get('classification') in {'fictional','deidentified'} and bool(g.get('reviewer')))
        return bool(classification_ok and g.get('allow_external') is True and g.get('revision')==doc['revision']
            and g.get('fingerprint')==fingerprint(doc) and doc['state']=='ready')
    except (OSError,ValueError,TypeError,AttributeError,sqlite3.Error):return False


def audit(data, action, details):
    # Callers construct metadata only: no key, document prose, question or model response.
    with closing(connect(data)) as c, c:
        c.execute('INSERT INTO external_audit(at,action,body) VALUES(?,?,?)',
            (datetime.now(timezone.utc).isoformat(),action,json.dumps(dict(details,operator='local_unauthenticated'),ensure_ascii=False)))


def status(data, doc):
    g=record(data,doc);ok=allowed(data,doc)
    return {'allowed':ok,'classification':g.get('classification') if ok else None,
        'revision':doc['revision'],'fingerprint':fingerprint(doc),
        'can_review':doc['state']=='ready' and bool(doc.get('admission',{}).get('eligible')),
        'operator':'local_unauthenticated','notice':'本机单人演示的人工确认；未验证操作员身份，不自动核实公开来源。'}


def update(data, doc, revision, expected_fingerprint, classification=None, checks=None, revoke=False):
    if type(revision) is not int or revision!=doc['revision'] or expected_fingerprint!=fingerprint(doc):
        raise ValueError('permission_version_changed')
    if not revoke and (doc['state']!='ready' or not doc.get('admission',{}).get('eligible')):
        raise ValueError('permission_document_unavailable')
    if not revoke and (classification not in CLASSES or not isinstance(checks,dict) or set(checks)!=set(CHECKS)
                       or any(checks[k] is not True for k in CHECKS)):
        raise ValueError('permission_checks_required')
    previous=record(data,doc)
    value={'document_id':doc['id'],'revision':doc['revision'],'fingerprint':fingerprint(doc),
        'classification':previous.get('classification') if revoke else classification,
        'checks':previous.get('checks',{}) if revoke else checks,'allow_external':not revoke,
        'mechanism':'local_human_confirmation','operator':'local_unauthenticated',
        'grant_id':str(uuid.uuid4()),'at':datetime.now(timezone.utc).isoformat()}
    with closing(connect(data)) as c, c:
        c.execute('INSERT OR REPLACE INTO external_permissions VALUES(?,?)',(doc['id'],json.dumps(value,ensure_ascii=False)))
        c.execute('INSERT INTO external_audit(at,action,body) VALUES(?,?,?)',
            (value['at'],'permission_revoked' if revoke else 'permission_granted',json.dumps(value,ensure_ascii=False)))
    return status(data,doc)

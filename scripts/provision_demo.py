"""Non-interactive equivalent of prepare_review.py for the local demo.

Creates the empty review library and three fictional accounts that exercise the
permission model (manager, R&D role, production role). No documents, no AI key.
"""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
os.environ['P18_DATA_DIR'] = str(ROOT / 'runtime/demo-v1-experience')
os.environ['P18_SEMANTIC_ENABLED'] = '0'
sys.path.insert(0, str(ROOT))

ACCOUNTS = [
    ('admin', 'p18-review-2026', '研发部员工', True),
    ('dev', 'p18-review-2026', '启辰研发岗位', False),
    ('prod', 'p18-review-2026', '启辰生产岗位', False),
    # One manager per department: the upload path refuses to create a document
    # its own author could not read, so seeding needs the matching identity.
    ('mgr_rd', 'p18-review-2026', '启辰研发岗位', True),
    ('mgr_mfg', 'p18-review-2026', '生产制造部员工', True),
]


def main():
    from app import main as store
    from app import library_store
    store.initialize()
    with store.connect() as conn:
        library_store.enable(conn)
        for username, password, identity, manager in ACCOUNTS:
            try:
                library_store.create_account(conn, username, password, identity, manager=manager)
            except Exception as exc:  # already provisioned
                print('skip', username, exc)
        conn.commit()
    print('ready:', store.DATA)


if __name__ == '__main__':
    main()

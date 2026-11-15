"""Local account provisioning. Explicit isolated data directory required.

Passwords are read interactively, never as command-line arguments.
"""
import argparse
import getpass
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import library_store
from app.library_policy import IDENTITIES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', required=True, type=Path)
    parser.add_argument('--username', required=True)
    parser.add_argument('--identity', required=True, choices=list(IDENTITIES))
    parser.add_argument('--manager', action='store_true')
    parser.add_argument('--enable', action='store_true', help='Enable managed mode on this database')
    args = parser.parse_args()
    password = getpass.getpass('新账号密码（至少12字符）：')
    if password != getpass.getpass('再次输入：'):
        raise SystemExit('两次密码不一致')
    args.data_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.data_dir / 'workbench.sqlite3') as conn:
        library_store.initialize(conn)
        library_store.create_account(conn, args.username, password, args.identity, manager=args.manager)
        if args.enable:
            library_store.enable(conn)
    print('账号已创建。未自动授予任何资料外发许可。')


if __name__ == '__main__':
    main()

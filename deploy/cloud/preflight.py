"""Read-only repository and imported-runtime checks before building containers."""
import argparse
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]


def check(root, runtime_required=True):
    errors = []
    for name in ['frontend/package-lock.json', 'frontend/src/main.tsx', 'app/main.py',
                 'config/business.example.json', 'config/experience_guard/sitecustomize.py',
                 'deploy/cloud/Dockerfile', 'deploy/cloud/compose.yaml', 'deploy/cloud/server.py',
                 'deploy/cloud/Caddyfile', 'requirements-semantic.txt', 'requirements-docling.txt', 'requirements-llm.txt']:
        if not (root / name).is_file():
            errors.append('缺少仓库文件：' + name)
    if runtime_required:
        env = root / 'deploy/cloud/.env'
        values = dict(line.split('=', 1) for line in env.read_text().splitlines() if '=' in line and not line.lstrip().startswith('#')) if env.is_file() else {}
        domain = values.get('P18_DOMAIN', '').strip()
        if domain == 'demo.your-domain.com' or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}', domain):
            errors.append('请在 deploy/cloud/.env 设置真实域名（不含协议、端口和路径）')
        marker = root / 'runtime/cloud-demo.json'
        if not marker.is_file() or json.loads(marker.read_text()).get('isolated_demo') is not True:
            errors.append('尚未导入资料包：缺少 runtime/cloud-demo.json')
        for name in ['demo-v1-experience', 'business-workflow']:
            db = root / 'runtime' / name / 'workbench.sqlite3'
            if not db.is_file():
                errors.append('缺少数据库：' + name)
                continue
            with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
                if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    errors.append('数据库完整性检查失败：' + name)
        if not (root / 'runtime/business-workflow/business-seed.json').is_file():
            errors.append('缺少业务资料读权映射 business-seed.json')
    return errors


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-only', action='store_true')
    args = parser.parse_args()
    try:
        errors = check(ROOT, not args.source_only)
    except (ValueError, OSError, sqlite3.Error) as error:
        errors = ['配置或数据库不可读取：' + str(error)]
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        raise SystemExit(1)
    print('仓库及资料包检查通过。Docker构建、域名/TLS、模型下载和问答速度仍需在服务器验证。')

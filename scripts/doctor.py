"""Environment self-check for a fresh checkout.

    .venv/bin/python scripts/doctor.py

Prints PASS/FAIL per prerequisite so a new machine can tell what is missing
before blaming the app. Never downloads anything and never opens the database
for writing.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = []


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))


def main():
    RESULTS.clear()
    check('Python ≥ 3.12', sys.version_info >= (3, 12), sys.version.split()[0])

    missing = [module for module in
               ('fastapi', 'uvicorn', 'pydantic', 'docx', 'openpyxl', 'fitz', 'olefile')
               if importlib.util.find_spec(module) is None]
    check('后端依赖', not missing, '缺失：' + ', '.join(missing) if missing else 'ok')

    semantic_missing = [module for module in ('torch', 'transformers', 'qdrant_client', 'huggingface_hub')
                        if importlib.util.find_spec(module) is None]
    check('语义检索依赖', not semantic_missing,
          '缺失：' + ', '.join(semantic_missing) if semantic_missing else 'ok')

    config = json.loads((ROOT / 'config/demo-v1.json').read_text())
    cache = ROOT / config['model_cache']
    revision = config['embedding_revision']
    snapshot = cache / 'models--Qwen--Qwen3-Embedding-0.6B' / 'snapshots' / revision
    check('Embedding 权重（固定 revision）', snapshot.is_dir() and any(snapshot.iterdir()),
          str(snapshot.relative_to(ROOT)))

    try:
        sys.path.insert(0, str(ROOT))
        from app.parser import soffice_path
        candidate=os.environ.get('SOFFICE_PATH') or config.get('converter') or soffice_path()
        resolved=Path(candidate) if candidate else None
        found = bool(resolved and resolved.is_file())
        detail = str(resolved) if resolved else '未找到：设置 SOFFICE_PATH 或安装 LibreOffice'
    except Exception as exc:  # missing deps already reported above
        found, detail = False, f'无法解析：{type(exc).__name__}'
    check('LibreOffice（DOC 转换 / Word 预览）', found, detail)

    data = ROOT / 'runtime/demo-v1-experience'
    has_data = (data / 'workbench.sqlite3').is_file()
    check('演示数据目录', has_data, str(data.relative_to(ROOT)) if has_data
          else '在新目录运行 scripts/prepare_review.py 创建自己的账号')

    build = ROOT / 'web/app/assets'
    has_build = build.is_dir() and any(build.glob('*.js'))
    check('前端构建产物', has_build, str(build.relative_to(ROOT)) if has_build
          else '先运行 (cd frontend && npm ci && npm run build)')

    port = socket.socket()
    busy = port.connect_ex(('127.0.0.1', 8896)) == 0
    port.close()
    ours=False
    if (data/'service.json').is_file():
        try:
            state=json.loads((data/'service.json').read_text())
            owners=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:8896','-sTCP:LISTEN','-t'],capture_output=True,text=True).stdout.split()
            cwd=subprocess.run(['/usr/sbin/lsof','-a','-p',str(state['pid']),'-d','cwd','-Fn'],capture_output=True,text=True).stdout
            ours=owners==[str(state['pid'])] and ('n'+str(ROOT)) in cwd
        except (OSError,ValueError,KeyError):pass
    if busy and ours:
        check('8896 端口', True, '体验服务已在运行')
    elif busy:
        check('8896 端口', False, '被其他进程占用，启动器会拒绝覆盖')
    else:
        check('8896 端口', True, '空闲')

    width = max(len(name) for name, _, _ in RESULTS)
    failed = 0
    for name, ok, detail in RESULTS:
        print(f"{'✅' if ok else '❌'} {name:<{width}}  {detail}")
        failed += 0 if ok else 1
    print(f"\n{len(RESULTS) - failed}/{len(RESULTS)} 通过")
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())

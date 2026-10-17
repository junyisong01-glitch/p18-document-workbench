"""One workbench launcher: check capabilities, preserve data, never stop old services."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.request import urlopen
import uuid

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.local_setup import check_local_runtime

VERSION = 'semantic-ui-v1'
URL = 'http://127.0.0.1:8765'


def probe(url=URL):
    try:
        with urlopen(url + '/api/config', timeout=2) as response:
            config = json.load(response)
        if config.get('scope') != 'local' or config.get('max_files') != 20:
            return None
        try:
            with urlopen(url + '/api/semantic', timeout=2) as response:
                semantic = json.load(response)
        except (OSError, ValueError):
            semantic = None
        return {'config': config, 'semantic': semantic}
    except (OSError, ValueError):
        return None


def healthy():
    return probe() is not None


def check_vector_lock(data):
    lock = data / 'qdrant/.lock'
    if lock.exists():
        import portalocker
        with lock.open('r+') as file:
            try:
                portalocker.lock(file, portalocker.LOCK_EX | portalocker.LOCK_NB)
                portalocker.unlock(file)
            except portalocker.exceptions.LockException as exc:
                raise RuntimeError('同一 Qdrant 数据目录正在被另一个服务占用；未启动第二个索引进程。') from exc


def backup_before_semantic(data):
    """Copy originals and a consistent SQLite snapshot before the first activation."""
    check_vector_lock(data)
    db = data / 'workbench.sqlite3'
    if not db.exists():
        return None
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as conn:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('原数据库完整性检查失败，未启用检索，请先核对数据。')
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'documents', 'events'} <= tables:
            raise RuntimeError('数据结构不兼容，未进行迁移或覆盖。')
        for row in conn.execute('SELECT body FROM documents'):
            doc = json.loads(row[0])
            if not {'id', 'state', 'revision'} <= doc.keys():
                raise RuntimeError('文档记录格式不兼容，未覆盖原数据。')
        size = db.stat().st_size + sum(p.stat().st_size for folder in ('files','qdrant')
              if (data/folder).exists() for p in (data/folder).rglob('*') if p.is_file())
        if shutil.disk_usage(data).free < size + 100_000_000:
            raise RuntimeError('磁盘空间不足以备份，未启用索引。')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]
        backup = data / 'backups' / ('before-semantic-' + stamp)
        backup.mkdir(parents=True)
        with sqlite3.connect(backup/'workbench.sqlite3') as target:
            conn.backup(target)
        for folder in ('files','qdrant'):
            if (data/folder).is_dir():
                shutil.copytree(data/folder, backup/folder)
        (backup/'README.txt').write_text('启用语义检索前的SQLite与文件副本。回退须先停止相应服务，再由用户确认恢复；不要覆盖仍在运行的数据库。', encoding='utf-8')
        return backup


def launch(open_browser=False, *, semantic=None, interactive=False, data_dir=None, port=8765):
    data = Path(data_dir or os.environ.get('P18_DATA_DIR', ROOT/'runtime')).expanduser().resolve()
    url = f'http://127.0.0.1:{port}'
    config_file = data / 'launcher.json'
    try:
        saved = json.loads(config_file.read_text()) if config_file.exists() else {}
    except (OSError, ValueError) as exc:
        raise RuntimeError('本地启动设置无法读取，请核对 launcher.json；未覆盖设置。') from exc
    desired = semantic if semantic is not None else saved.get('semantic_enabled')
    existing = probe(url)
    if existing:
        if existing['config'].get('workbench_version') != VERSION or existing['semantic'] is None:
            raise RuntimeError(f'{url} 正在运行旧版本，虽然文档服务正常，但未确认语义检索能力。未自动停止服务。请先确认备份及安全重启，再使用原启动入口。')
        if Path(existing['config'].get('data_directory','')).resolve() != data:
            raise RuntimeError('当前端口使用不同的数据目录，未切换、覆盖或启动第二份工作台。')
        actual = existing['semantic'].get('enabled') is True
        if desired is not None and actual != desired:
            raise RuntimeError('已有服务的语义检索启用状态与请求不同。未自动重启；请确认后安全停止该服务再启动。')
        print('复用原工作台：' + url)
        print('本地语义检索已启用。' if actual else '文档管理可用；本地语义检索未启用。')
        if existing['semantic'].get('error'):
            print('检索状态提示：' + str(existing['semantic']['error']))
    else:
        with socket.socket() as connection:
            if connection.connect_ex(('127.0.0.1',port)) == 0:
                raise RuntimeError(f'端口 {port} 被其他服务占用，未停止任何服务。')
        # Do not accidentally run the formal runtime on a second known port.
        for other in (8765,8766,8767):
            if other == port: continue
            running = probe(f'http://127.0.0.1:{other}')
            if running:
                directory = running['config'].get('data_directory')
                if directory and Path(directory).resolve() == data or (not directory and other==8765 and data==ROOT/'runtime'):
                    raise RuntimeError(f'同一数据目录可能由端口{other}的服务使用，未启动第二个实例。')
        python = ROOT/'.venv/bin/python'
        if not python.exists():
            raise RuntimeError('缺少项目运行环境，请先按 README 安装依赖。')
        setup = check_local_runtime()
        if desired is None and interactive and setup['ready']:
            print('资料目录：' + str(data))
            print('首次启用会先备份原件和数据库，再对符合原入库规则的片段建立本地索引；不改变审核结论、不外发资料。')
            desired = input('启用本地知识检索，并保存本次选择？[y/N] ').strip().lower() == 'y'
        desired = bool(desired)
        enabled = desired and setup['ready']
        print(setup['message'])
        if desired and not enabled:
            print('本次先启动文档管理；检索未启用。补齐依赖或手动下载模型后，需要安全重启。')
        data.mkdir(parents=True, exist_ok=True)
        if enabled:
            check_vector_lock(data)
        backup = None
        if enabled and not saved.get('semantic_prepared'):
            backup = backup_before_semantic(data)
            if backup: print('启用前备份：' + str(backup))
        environment = os.environ.copy()
        environment['P18_DATA_DIR'] = str(data)
        environment['P18_SEMANTIC_ENABLED'] = '1' if enabled else '0'
        with (data/'server.log').open('ab') as log:
            process = subprocess.Popen([str(python),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(port),'--workers','1'],
                cwd=ROOT,env=environment,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        started = None
        for _ in range(120):
            started = probe(url)
            if started and started['config'].get('workbench_version') == VERSION:
                break
            if process.poll() is not None:
                raise RuntimeError('服务启动失败。原数据和备份保留，请核对对应目录的server.log。')
            time.sleep(.25)
        else:
            raise RuntimeError('等待启动超时，未自动终止进程；请核对日志与端口后再操作。')
        (data/'server.pid').write_text(str(process.pid))
        settings = {'semantic_enabled': desired, 'semantic_prepared': saved.get('semantic_prepared',False) or enabled,
                    'last_backup': str(backup) if backup else saved.get('last_backup')}
        config_file.write_text(json.dumps(settings, ensure_ascii=False, indent=2),encoding='utf-8')
        print('文档工作台已就绪：' + url)
        if enabled and not started['semantic'].get('enabled'):
            print('索引服务未就绪，文档管理继续可用，请查看页面中的真实原因。')
        elif enabled: print('本地语义检索已启用，符合条件的资料会自动排队建立索引。')
        else: print('文档管理已启动；本地语义检索未启用。可在下次安全启动时选择开启。')
    print('可以关闭此终端；已有服务不会被本启动器自动停止。')
    if open_browser:
        subprocess.run(['open',url],check=True)
    return url


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--open',action='store_true')
    parser.add_argument('--interactive',action='store_true')
    flags = parser.add_mutually_exclusive_group()
    flags.add_argument('--enable-semantic',dest='semantic',action='store_true',default=None)
    flags.add_argument('--disable-semantic',dest='semantic',action='store_false')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--data-dir')
    args = parser.parse_args()
    try:
        launch(args.open,semantic=args.semantic,interactive=args.interactive,data_dir=args.data_dir,port=args.port)
    except (RuntimeError,OSError,ValueError,sqlite3.Error,subprocess.CalledProcessError) as exc:
        print(str(exc),file=sys.stderr)
        sys.exit(1)

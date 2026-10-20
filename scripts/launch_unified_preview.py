"""Single safe entry for the existing 8774 fictional library. Never stops a service."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
DATA=Path('/private/tmp/p18-qa-8774-D-20261020')
URL='http://127.0.0.1:8774'


def validate_data(data):
    data=Path(data).resolve()
    if (not data.is_relative_to(Path('/private/tmp')) or not data.name.startswith('p18-qa-8774-')
        or not (data/'.qa-integration-fixture').is_file() or not (data/'workbench.sqlite3').is_file()):
        raise ValueError('仅允许既有、已标记的8774虚构测试库；未创建、迁移或覆盖任何数据库。')
    return data


def probe(data, fetch=None):
    def get(path):
        if fetch:return fetch(path)
        with urlopen(URL+path,timeout=2) as response:return json.load(response)
    try:
        status=get('/api/unified-preview');config=get('/api/config');rag=get('/api/rag')
        return bool(status.get('ui_version')=='P18-UI-001' and status.get('port')==8774
            and status.get('provider_mode')=='offline_capture' and status.get('external_requests_enabled') is False
            and Path(status.get('data_directory','')).resolve()==data
            and Path(config.get('data_directory','')).resolve()==data
            and rag.get('provider')=='模拟回答 · 未调用外部API')
    except (OSError,ValueError,TypeError):return False


def occupied():
    with socket.socket() as check:
        check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:check.bind(('127.0.0.1',8774));return False
        except OSError:return True


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,default=DATA);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    try:data=validate_data(args.data_dir)
    except ValueError as error:parser.error(str(error))
    if occupied():
        if not probe(data):parser.error('8774已有其他或旧版服务；本入口不会停止它。请核对环境后再处理。')
        print('8774统一测试工作台已运行，已核对虚构数据路径和模拟服务。',flush=True)
        if not args.no_browser:webbrowser.open(URL)
        return
    command=['/usr/bin/env','-u','DEEPSEEK_API_KEY',sys.executable,str(ROOT/'scripts/serve_qa_interactions.py'),'--data-dir',str(data)]
    child=subprocess.Popen(command,cwd=ROOT)
    print('正在启动8774；无需密钥，不调用真实DeepSeek。',flush=True)
    for _ in range(60):
        if child.poll() is not None:raise SystemExit('隔离服务未能启动；没有停止任何其他环境。')
        if probe(data):
            print('打开 '+URL+'；文档管理、知识检索和知识问答共用此隔离库。请保留本终端。',flush=True)
            if not args.no_browser:webbrowser.open(URL)
            break
        time.sleep(.3)
    else:raise SystemExit('暂未核验到就绪状态，请查看当前服务日志；未自动重复启动或结束进程。')
    try:child.wait()
    except KeyboardInterrupt:
        # Only this invocation's own child; never an existing listener.
        child.terminate();child.wait(timeout=15)


if __name__=='__main__':main()

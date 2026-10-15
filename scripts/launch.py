"""Double-click launcher: reuse healthy local server or start and verify it."""
import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
URL = "http://127.0.0.1:8765"


def healthy():
    try:
        with urlopen(URL + "/api/config", timeout=1) as response:
            result = json.load(response)
        return result.get("scope") == "local" and result.get("max_files") == 20 and "indexing" in result
    except (OSError, ValueError):
        return False


def launch(open_browser=False):
    if not healthy():
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", 8765)) == 0:
                raise RuntimeError("端口 8765 已被其他服务占用。未停止任何进程，请让助手协助检查。")
        python = ROOT / ".venv/bin/python"
        if not python.exists():
            raise RuntimeError("缺少项目 Python 环境，请先按 README.md 安装依赖。")
        runtime = ROOT / "runtime"
        runtime.mkdir(exist_ok=True)
        with (runtime / "server.log").open("ab") as log:
            process = subprocess.Popen([str(python), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765"],
                                       cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                       start_new_session=True)
        for _ in range(60):
            if healthy():
                (runtime / "server.pid").write_text(str(process.pid))
                break
            if process.poll() is not None:
                raise RuntimeError("服务启动失败。可查看 runtime/server.log，或让助手检查；不会覆盖已有文档。")
            time.sleep(.25)
        else:
            process.terminate()
            raise RuntimeError("等待启动超时，请查看 runtime/server.log 后重试。")
    print("文档工作台已就绪：" + URL)
    print("可以关闭这个终端窗口；服务继续在本机运行。电脑重启后请再次双击启动入口。")
    if open_browser:
        subprocess.run(["open", URL], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    try:
        launch(args.open)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

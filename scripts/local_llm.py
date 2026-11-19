"""Start the already-installed local answer service; never download or use cloud."""
from pathlib import Path
import json, os, shutil, socket, subprocess, time
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[1]

def tags():
    with build_opener(ProxyHandler({})).open(Request('http://127.0.0.1:11434/api/tags'), timeout=2) as response:
        return json.loads(response.read(1000000))

def ensure_local_service():
    from app.llm import load_env
    load_env(ROOT / '.env')
    if os.environ.get('LLM_PROVIDER') != 'ollama':
        return
    model = os.environ.get('OLLAMA_MODEL', 'qwen2.5:7b')
    try:
        value = tags()
    except Exception:
        value = None
    if value is not None:
        if not any(item.get('name') == model or item.get('model') == model for item in value.get('models', [])):
            raise RuntimeError('Ollama已启动，但没有配置的本地模型；不会下载或改用外部API。')
        print('本地回答服务已就绪：' + model)
        return
    with socket.socket() as connection:
        if connection.connect_ex(('127.0.0.1', 11434)) == 0:
            raise RuntimeError('11434端口已被其他服务占用，未覆盖启动。')
    binary = next((str(path) for path in [Path('/usr/local/bin/ollama'), Path('/opt/homebrew/bin/ollama'), Path('/Applications/Ollama.app/Contents/Resources/ollama')] if path.is_file()), None)
    binary = binary or shutil.which('ollama')
    models = ROOT / '.optional/ollama/models'
    if not binary or not models.is_dir():
        raise RuntimeError('本地Ollama或已安装模型缺失；不会下载或改用外部API。')
    state = ROOT / 'runtime/local-llm'
    state.mkdir(parents=True, exist_ok=True)
    home = ROOT / '.local-home'
    home.mkdir(exist_ok=True)
    env = dict(PATH='/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin', HOME=str(home),
               OLLAMA_HOST='127.0.0.1:11434', OLLAMA_MODELS=str(models),
               OLLAMA_NO_CLOUD='1', OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='1',
               OLLAMA_KEEP_ALIVE='0', NO_PROXY='*', no_proxy='*')
    with (state / 'server.log').open('a') as log:
        process = subprocess.Popen([binary, 'serve'], cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    (state / 'service.json').write_text(json.dumps({'pid': process.pid, 'port': 11434, 'model_dir': str(models)}))
    for _ in range(100):
        if process.poll() is not None:
            break
        try:
            value = tags()
            if any(item.get('name') == model or item.get('model') == model for item in value.get('models', [])):
                print('已启动本地回答服务：' + model)
                return
        except Exception:
            pass
        time.sleep(.2)
    raise RuntimeError('本地回答服务未就绪，请查看runtime/local-llm/server.log；检索仍可用，不会自动外发。')

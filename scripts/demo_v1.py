"""Use --check for preflight; default runs this isolated localhost app only."""
from pathlib import Path
import json,socket,subprocess,sys
from demo_env import ROOT,environment
def main():
    cfg=json.loads((ROOT/'config/demo-v1.json').read_text())
    if cfg['port'] in {8765,8876,8892}:raise SystemExit('Protected port refused')
    if (ROOT/'.venv').is_symlink() or not (ROOT/'.venv/bin/python').is_file():raise SystemExit('Independent environment missing')
    for rel in [cfg['data_dir'],cfg['model_cache']]:
        if not (ROOT/rel).resolve().is_relative_to(ROOT):raise SystemExit('Unsafe local storage path')
    with socket.socket() as probe:probe.bind((cfg['host'],cfg['port']))
    env=environment()
    if '--check' in sys.argv:
        code="from app.local_setup import check_local_runtime; import json; r=check_local_runtime(); print(json.dumps(r,ensure_ascii=False)); raise SystemExit(not r['ready'])"
        subprocess.run([str(ROOT/'.venv/bin/python'),'-B','-c',code],cwd=ROOT,env=env,check=True)
        print('Ready: http://'+cfg['host']+':'+str(cfg['port'])+' ; external QA disabled; preflight only')
        return
    subprocess.run([str(ROOT/'.venv/bin/python'),'-B','-m','uvicorn','app.main:app','--host',cfg['host'],'--port',str(cfg['port']),'--workers','1'],cwd=ROOT,env=env,check=True)
if __name__=='__main__':main()

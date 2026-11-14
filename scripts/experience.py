"""Simple local product entry. Credentials are never persisted."""
from pathlib import Path
import sys,os,json,socket,subprocess,time,signal,getpass,argparse,shutil
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scripts'))
from demo_env import environment
DATA=R/'runtime/demo-v1-experience';STATE=DATA/'service.json'
def listener():
 with socket.socket()as s:return s.connect_ex(('127.0.0.1',8896))==0
def main():
 p=argparse.ArgumentParser();p.add_argument('--local',action='store_true');p.add_argument('--ai',action='store_true');p.add_argument('--stop',action='store_true');p.add_argument('--status',action='store_true');p.add_argument('--acceptance',action='store_true');a=p.parse_args()
 if a.status:print('8896正在运行'if listener()else'8896未运行');return
 if a.stop:
  if not STATE.exists()or not listener():print('体验服务未运行');return
  state=json.loads(STATE.read_text());pid=state['pid']
  cwd=subprocess.run(['/usr/sbin/lsof','-a','-p',str(pid),'-d','cwd','-Fn'],capture_output=True,text=True).stdout
  owners=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:8896','-sTCP:LISTEN','-t'],capture_output=True,text=True).stdout.split()
  if owners!=[str(pid)]or ('n'+str(R))not in cwd:raise SystemExit('8896不属于本体验服务，未停止。')
  os.kill(pid,signal.SIGINT)
  for _ in range(150):
   if not listener():print('体验服务已停止；资料和账号保留。');return
   time.sleep(.1)
  raise SystemExit('服务仍在收尾，未强制结束。')
 if listener():
  if not STATE.exists():raise SystemExit('8896被其他服务占用，未覆盖启动。')
  existing=json.loads(STATE.read_text());owners=subprocess.run(['/usr/sbin/lsof','-nP','-iTCP:8896','-sTCP:LISTEN','-t'],capture_output=True,text=True).stdout.split()
  if owners!=[str(existing['pid'])]:raise SystemExit('8896不是本次体验服务，未覆盖启动。')
  print('体验版已经运行：http://127.0.0.1:8896/library/')
  if not(a.local or a.acceptance):subprocess.run(['/usr/bin/open','http://127.0.0.1:8896/library/'])
  return
 if not DATA.exists()or not(DATA/'workbench.sqlite3').exists():raise SystemExit('统一体验数据尚未准备好。')
 mode='local'
 if a.acceptance:mode='acceptance'
 elif a.ai:mode='ai'
 elif not a.local:
  print('1 本地资料与检索（不启用AI）\n2 启用真实AI（仅审核过的虚构公开资料；可能产生费用）')
  if input('请选择1或2，默认1：').strip()=='2':mode='ai'
 key=''
 if mode=='ai':
  if not sys.stdin.isatty():raise SystemExit('请在本机终端隐藏输入，不接受命令参数传递密钥。')
  key=getpass.getpass('DeepSeek API Key（隐藏输入，仅本次运行有效）：').strip()
  if not key:print('未输入密钥，改为本地模式。');mode='local'
 env=environment();env.update(P18_DATA_DIR=str(DATA),TMPDIR=str(DATA/'tmp'),PYTHONPATH=str(R/'config/experience_guard')+os.pathsep+str(R),P18_DEEPSEEK_BASE_URL='https://api.deepseek.com',P18_DEEPSEEK_MODEL='deepseek-flash',P18_DEEPSEEK_TIMEOUT='60',P18_DEEPSEEK_MAX_TOKENS='1500',no_proxy='*',NO_PROXY='*')
 if mode=='acceptance':env['P18_EXPERIENCE_ACCEPTANCE']='1'
 # Explicit operator configuration (gateway target/key, parser backend) passes through;
 # nothing is defaulted or persisted here.
 env.update({k:v for k,v in os.environ.items() if k.startswith('P18_') and k not in env})
 log=(DATA/'server.log').open('a')
 proc=subprocess.Popen([str(R/'.venv/bin/python'),'-B',str(R/'scripts/experience_server.py')],cwd=R,env=env,stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT,text=True,start_new_session=True)
 proc.stdin.write(json.dumps({'api_key':key})+chr(10));proc.stdin.close();key=None;log.close()
 for _ in range(200):
  if proc.poll()is not None:raise SystemExit('启动失败，请查看本机运行日志。')
  if listener():break
  time.sleep(.15)
 else:raise SystemExit('启动超时，请核对日志，勿重复启动。')
 STATE.write_text(json.dumps({'pid':proc.pid,'port':8896,'data_dir':str(DATA),'mode':mode,'api_key_persisted':False,'started_at':time.time()},ensure_ascii=False,indent=2));os.chmod(STATE,0o600)
 print('已启动：http://127.0.0.1:8896/library/；模式：'+mode+'。可关闭此终端，服务继续运行。')
 if not(a.local or a.acceptance):subprocess.run(['/usr/bin/open','http://127.0.0.1:8896/library/'])
if __name__=='__main__':main()

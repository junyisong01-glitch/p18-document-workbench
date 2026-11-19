"""Persistent local experience entry; native client/protocol, official-only egress."""
from pathlib import Path
import os,sys,json,time,threading
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R))
DATA=R/'runtime/demo-v1-experience';TEST=os.environ.get('P18_EXPERIENCE_ACCEPTANCE')=='1'
if __name__=='__main__':
 if TEST:
  os.environ['DEEPSEEK_API_KEY']='synthetic-offline-acceptance-only'
  os.environ['LLM_PROVIDER']='deepseek'
 else:
  value=json.loads(sys.stdin.readline());key=value.pop('api_key','');value.clear()
  if key:os.environ['DEEPSEEK_API_KEY']=key
  key=None
else:os.environ.pop('DEEPSEEK_API_KEY',None)
import app.rag as rag
from app import main,library_api,egress
from sitecustomize import official_deepseek_request
from contextlib import nullcontext
from urllib.request import ProxyHandler
_original=rag.secure_urlopen
_lock=threading.Lock()
def metadata_event(record):
 with _lock:
  with (DATA/'ai-requests.jsonl').open('a')as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
class Response:
 def __init__(self,r,record):self.r=r;self.record=record
 def __enter__(self):self.r.__enter__();return self
 def __exit__(self,*a):return self.r.__exit__(*a)
 def read(self,n):
  data=self.r.read(n)
  try:
   j=json.loads(data);metadata_event(dict(self.record,event='response',model=j.get('model'),usage=j.get('usage')))
  except(ValueError,TypeError):pass
  return data
 def __getattr__(self,n):return getattr(self.r,n)
if TEST:
 from scripts.acceptance_fixture import OfflineResponse
 rag.DeepSeekClient.label='验收模拟（未调用DeepSeek）'
_native_external_allowed=rag.RagService.external_allowed
def experience_external_allowed(self,doc):
 if not _native_external_allowed(self,doc):return False
 row=library_api.metadata(self.store,doc['id']);grant=egress.record(self.store.DATA,doc)
 return bool(row and row[1].classification=='公开' and row[1].lifecycle=='现行有效' and grant.get('classification')=='fictional')
rag.RagService.external_allowed=experience_external_allowed
def checked_transport(req,timeout):
 if req.full_url!='https://api.deepseek.com/chat/completions'or req.get_method()!='POST':raise rag.RagError('destination_not_allowed','仅允许官方DeepSeek问答接口，未发送。')
 body=json.loads(req.data)
 if body.get('model')!='deepseek-flash' or body.get('stream')is not False or body.get('thinking')!={'type':'disabled'}:raise rag.RagError('configuration_changed','接收配置不符，未发送。')
 payload=json.loads(body['messages'][-1]['content']);groups=payload.get('untrusted_evidence',[])
 if not groups:raise rag.RagError('evidence_missing','没有获准证据，未发送。')
 for group in groups:
  for source in group.get('members',[group]):
   d=main.available(source['document_id']);row=library_api.metadata(main,d['id']);grant=egress.record(DATA,d)
   if not row or row[1].classification!='公开' or row[1].lifecycle!='现行有效' or grant.get('classification')!='fictional' or not egress.allowed(DATA,d):raise rag.RagError('experience_fictional_only','体验版仅允许已逐份审核的虚构公开资料；未发送。')
 record={'at':time.time(),'event':'attempt','simulated':TEST,'messages_hash':rag.digest(body['messages']),'destination':req.full_url,'model':body['model']};metadata_event(record)
 if TEST:return Response(OfflineResponse(),record)
 # The audited native transport remains responsible for HTTPS, timeout and NoRedirect.
 try:
  with official_deepseek_request():return Response(_original(req,timeout),record)
 except Exception as e:metadata_event(dict(record,event='error',error_type=type(e).__name__));raise
rag.secure_urlopen=checked_transport

from app.llm import DeepSeekProvider, messages as controlled_messages
_sdk_generate=DeepSeekProvider.generate
def checked_sdk_generate(self,prompt):
 body={'model':'deepseek-flash','stream':False,'thinking':{'type':'disabled'},'messages':controlled_messages(prompt)}
 payload=json.loads(body['messages'][-1]['content'])
 groups=payload.get('untrusted_evidence',[])
 if not groups:raise rag.RagError('evidence_missing','没有获准证据，未发送。')
 for group in groups:
  for source in group.get('members',[group]):
   d=main.available(source['document_id']);row=library_api.metadata(main,d['id']);grant=egress.record(DATA,d)
   if not row or row[1].classification!='公开' or row[1].lifecycle!='现行有效' or grant.get('classification')!='fictional' or not egress.allowed(DATA,d):raise rag.RagError('experience_fictional_only','体验版仅允许已逐份审核的虚构公开资料；未发送。')
 record={'at':time.time(),'event':'attempt','simulated':TEST,'messages_hash':rag.digest(body['messages']),'destination':'https://api.deepseek.com/chat/completions','model':'deepseek-flash'}
 metadata_event(record)
 try:
  if TEST:
   with OfflineResponse()as response:result=json.loads(response.read(2000000))['choices'][0]['message']['content']
  else:
   with official_deepseek_request():result=_sdk_generate(self,prompt)
  metadata_event(dict(record,event='response'));return result
 except Exception as error:metadata_event(dict(record,event='error',error_type=type(error).__name__));raise
DeepSeekProvider.generate=checked_sdk_generate

import uvicorn
if __name__=='__main__':
 from app.datasets import install
 application=install(main)
 try:uvicorn.run(application,host='127.0.0.1',port=8896,workers=1)
 finally:os.environ.pop('DEEPSEEK_API_KEY',None)

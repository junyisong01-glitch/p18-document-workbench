"""Explicit isolated browser harness: real retrieval, simulated API; NEVER calls DeepSeek."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


class SimulatedClient:
    label='模拟API验收（未调用DeepSeek）'
    configured=True
    calls=0
    def complete(self,messages,cfg):
        self.__class__.calls+=1
        from app.rag import UNKNOWN
        payload=json.loads(messages[-1]['content']);question=payload['question'];evidence=payload['untrusted_evidence']
        source=next((s for s in evidence if '项目负责人：林晓岚' in s['text']),None)
        if not source or any(word in question for word in ['密码','住址','不存在']):answer=UNKNOWN;ids=[]
        else:
            id=source['id'];ids=[id]
            answer=('该虚构项目的导师也是林晓岚。' if '导师' in question else '该虚构项目的预约时长上限为90分钟。' if '时长' in question else '该虚构项目的负责人为林晓岚。')+'['+id+']'
        return json.dumps({'answer':answer,'citations':ids},ensure_ascii=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--port',type=int,default=8769);a=p.parse_args()
    if a.port in {8765,8766,8767,8768}:p.error('Only a new isolated port is allowed.')
    if not a.data_dir.resolve().is_relative_to(Path('/private/tmp')) and 'p18-rag-' not in str(a.data_dir):p.error('Use a new explicit temporary RAG test directory.')
    os.environ['P18_DATA_DIR']=str(a.data_dir.resolve());os.environ['P18_SEMANTIC_ENABLED']='1'
    import app.rag as rag
    rag.DeepSeekClient=SimulatedClient
    from app import main
    @main.app.get('/api/test-rag-demo')
    def demo_count():return {'simulated_calls':SimulatedClient.calls,'real_paid_calls':0}
    import uvicorn
    uvicorn.run(main.app,host='127.0.0.1',port=a.port,workers=1)

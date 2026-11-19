#!/usr/bin/env python3
"""Compare one public synthetic RAG question. Never reads corporate files or databases."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.llm import RoutedClient,ClientAdapter,load_env,guard,startup_check
from app.rag import config,RagService,RagError

def main():
    p=argparse.ArgumentParser();p.add_argument('--env',default='.env');p.add_argument('--health-only',action='store_true');p.add_argument('--confirm-external',action='store_true');args=p.parse_args()
    load_env(args.env);c=RoutedClient();status=startup_check();print(json.dumps(status,ensure_ascii=False))
    if args.health_only:return 2 if status.get('available') is False else 0
    if c.name=='ollama' and status.get('available') is False:
        if not sys.stdin.isatty():return 2
        if input('仅有公开虚构资料。输入 DEEPSEEK 确认降级，否则退出：')!='DEEPSEEK':return 2
        c.confirm_fallback()
        # A second confirmation below concerns the exact outbound payload, not just routing.
    evidence=[{'id':'S1','text':'【公开虚构测试】星舟项目的负责人为林晓岚，验收日期为2030年1月2日。','document_name':'synthetic-public'}]
    question='星舟项目由谁负责，何时验收？'
    msg=RagService.messages(question,[],evidence);cfg=c.configuration(config())
    print(json.dumps({'provider':c.name,'model':cfg['model'],'question':question,'messages':msg},ensure_ascii=False,indent=2))
    if c.name=='deepseek' and not args.confirm_external:
        if not sys.stdin.isatty() or input('核对以上虚构资料，输入 SEND 确认本轮外发：')!='SEND':return 2
    guard('demo',c.name)
    raw=ClientAdapter(c,cfg).generate(json.dumps(msg,ensure_ascii=False))
    state,answer,citations=RagService.validate_answer(raw,evidence)
    print(json.dumps({'provider':c.name,'status':state,'answer':answer,'citations':[x['id'] for x in citations]},ensure_ascii=False,indent=2));return 0
if __name__=='__main__':
    try:sys.exit(main())
    except RagError as e:print(json.dumps({'code':e.code,'error':str(e)},ensure_ascii=False),file=sys.stderr);sys.exit(2)

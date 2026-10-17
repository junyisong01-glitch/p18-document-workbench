"""Read-only API evaluation on an explicitly isolated localhost port.
No indexing requests, no model loading, no database writes.
"""
import argparse
import json
import statistics
import time
from pathlib import Path
from urllib.request import Request, urlopen


def request(port, body):
    req=Request(f'http://127.0.0.1:{port}/api/search',data=json.dumps(body).encode(),
                headers={'Content-Type':'application/json','X-P18-Client':'workbench'})
    start=time.perf_counter()
    with urlopen(req,timeout=120) as r:result=json.load(r)
    return result,(time.perf_counter()-start)*1000


def metrics(results,gold):
    targets=set(gold);ranks=[];got=set()
    for rank,hit in enumerate(results,1):
        members=hit.get('members',[hit]);found={m['chunk_id'] for m in members};got|=found
        if found&targets:ranks.append(rank)
    return {'top1':int(bool(ranks and ranks[0]==1)),'hit5':int(bool(ranks)),
            'recall5':len(got&targets)/len(targets) if targets else None,
            'mrr5':1/ranks[0] if ranks else 0,'answer_rank':ranks[0] if ranks else None}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--cases',required=True);p.add_argument('--output',required=True)
    args=p.parse_args()
    if args.port in {8765,8766,8767}:p.error('Use an isolated service port; protected ports are not accepted.')
    cases=json.loads(Path(args.cases).read_text())['cases'];output=[]
    for case in cases:
        modes={}
        for mode in ['vector','hybrid','hybrid_dedup']:
            response,ms=request(args.port,{'query':case['query'],'mode':mode})
            assert response['retrieval_mode']==mode
            assert len(response['results'])<=5
            modes[mode]={'metrics':metrics(response['results'],case['gold']),'ms':ms,'results':response['results']}
        output.append(dict(case,modes=modes))
    summary={}
    for mode in ['vector','hybrid','hybrid_dedup']:
        chosen=[c['modes'][mode]['metrics'] for c in output if c['gold']]
        summary[mode]={k:statistics.mean(r[k] for r in chosen) for k in ['top1','hit5','recall5','mrr5']}
        summary[mode]['median_ms']=statistics.median(c['modes'][mode]['ms'] for c in output)
        summary[mode]['no_answer_with_neighbors']=sum(bool(c['modes'][mode]['results']) for c in output if not c['gold'])
    result={'summary':summary,'cases':output}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(summary,ensure_ascii=False,indent=2))

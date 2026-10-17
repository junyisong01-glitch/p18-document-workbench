"""Offline retrieval comparison. Input: saved API candidates; never opens runtime DB/Qdrant.

Usage: python scripts/experiments/retrieval_quality.py INPUT.json OUTPUT.json
No fitting or gold-aware ranking; labels are used only by metrics.
"""
import collections
import json
import math
import re
import sqlite3
import statistics
import sys
import time
import unicodedata


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip()


def tokens(text):
    # General character bigrams for Han; Latin identifiers/numbers stay intact.
    out = []
    for run in re.findall(r'[\u3400-\u9fff]+|[a-z0-9_]+', normalize(text).lower()):
        if re.fullmatch(r'[a-z0-9_]+', run):
            out.append(run)
        elif len(run) == 1:
            out.append(run)
        else:
            out.extend(run[i:i+2] for i in range(len(run)-1))
    return out


def bm25(query, corpus):
    words = set(tokens(query)); docs = [collections.Counter(tokens(h['text'])) for h in corpus]
    n = len(docs); avg = sum(sum(d.values()) for d in docs) / n
    df = {w:sum(w in d for d in docs) for w in words}
    scores = []
    for hit,d in zip(corpus,docs):
        length = sum(d.values()); value = 0
        for w in words:
            freq = d[w]
            if freq:
                idf=math.log(1+(n-df[w]+.5)/(df[w]+.5))
                value += idf*freq*2.2/(freq+1.2*(.25+.75*length/avg))
        if value > 0:scores.append((value,hit))
    return [h for _,h in sorted(scores,key=lambda p:(-p[0],p[1]['chunk_id']))]


def fuse(vector, lexical, k=60):
    scores=collections.defaultdict(float); lookup={}
    for ranking in (vector,lexical):
        for rank,hit in enumerate(ranking,1):
            scores[hit['chunk_id']]+=1/(k+rank);lookup[hit['chunk_id']]=hit
    return [dict(lookup[cid],fusion_score=scores[cid]) for cid in sorted(scores,key=lambda cid:(-scores[cid],cid))]


def duplicate_key(hit):
    # Do not normalize indentation, table cells, or compatibility symbols away.
    text=unicodedata.normalize('NFC', hit['text'].replace('\r\n','\n'))
    if hit.get('kind') not in {'code','table','pdf_page'}:
        text=re.sub(r'\s+', ' ', text).strip()
    return (text,hit.get('kind'),hit.get('revision'),hit.get('chunk_config_hash'),hit.get('table_structure_hash'))


def groups(ranking):
    result=[]; seen={}
    for hit in ranking:
        # Version/config stays explicit per member. No document or source is deleted.
        key=duplicate_key(hit)
        member={k:hit[k] for k in ['document_id','document_name','chunk_id','revision','sources','index_token','chunk_config_hash']}
        if key in seen:
            result[seen[key]]['members'].append(member)
        else:
            seen[key]=len(result);result.append(dict(hit,members=[member]))
    return result


def ids(hit):
    return {m['chunk_id'] for m in hit.get('members',[hit])}


def evaluate(ranking,gold):
    top=ranking[:5]; relevant=set(gold)
    ranks=[i for i,h in enumerate(top,1) if ids(h)&relevant]
    retrieved=set().union(*(ids(h) for h in top)) if top else set()
    return {'top1':int(bool(top and ids(top[0])&relevant)), 'hit5':int(bool(ranks)),
            'recall5':len(retrieved&relevant)/len(relevant) if relevant else None,
            'mrr5':1/min(ranks) if ranks else 0,
            'duplicates5':len(top)-len({duplicate_key(h) for h in top}),
            'documents5':len({m['document_id'] for h in top for m in h.get('members',[h])}),
            'first_relevant_rank':next((i for i,h in enumerate(ranking,1) if ids(h)&relevant),None)}


def run(data):
    cases=data['cases']; results=[]; timing=collections.defaultdict(list)
    for case in cases:
        v=case['results']; lex=bm25(case['query'],v)
        methods={'vector5':v[:5],'vector10':v[:10],'vector20':v[:20],
                 'vector20_dedup':groups(v[:20]),'hybrid20':fuse(v[:20],lex[:20]),
                 'hybrid20_dedup':groups(fuse(v[:20],lex[:20]))}
        for name in methods:
            for _ in range(20):
                start=time.perf_counter()
                if name.startswith('hybrid'):
                    ranking=fuse(v[:20],bm25(case['query'],v)[:20]);ranking=groups(ranking) if name.endswith('dedup') else ranking
                elif name.endswith('dedup'):ranking=groups(v[:20])
                else:ranking=v[:int(name[6:])]
                timing[name].append((time.perf_counter()-start)*1000)
        results.append({'id':case['id'],'query':case['query'],'gold':case['gold'],'allow_no_answer':case['allow_no_answer'],
                        'methods':{name:{'metrics':evaluate(rank,case['gold']),'top5':rank[:5],
                                         'candidate_recall':len(set(case['gold'])&set().union(*(ids(h) for h in rank)))/len(case['gold']) if case['gold'] else None}
                                   for name,rank in methods.items()}})
    summary={}
    for name in results[0]['methods']:
        answerable=[r['methods'][name]['metrics'] for r in results if r['gold']]
        summary[name]={m:statistics.mean(x[m] for x in answerable) for m in ['top1','hit5','recall5','mrr5','duplicates5','documents5']}
        summary[name]['candidate_recall']=statistics.mean(r['methods'][name]['candidate_recall'] for r in results if r['gold'])
        summary[name]['extra_ms_median']=statistics.median(timing[name]);summary[name]['extra_ms_max']=max(timing[name])
        summary[name]['no_answer_returns']=sum(bool(r['methods'][name]['top5']) for r in results if not r['gold'])
    with sqlite3.connect(':memory:') as c:
        try:
            c.execute('create virtual table f using fts5(text)');c.execute('insert into f values (?)',('项目负责人 辛腾飞',))
            fts={'available':True,'default_unicode61_infix_matches':c.execute("select count(*) from f where f match '负责人'").fetchone()[0],
                 'default_unicode61_full_token_matches':c.execute("select count(*) from f where f match '项目负责人'").fetchone()[0]}
        except sqlite3.OperationalError as e:fts={'available':False,'error':str(e)}
    return {'parameters':{'vector_candidate_k':[5,10,20],'display_k':5,'lexical':'Han-bigram/Latin-token BM25 k1=1.2 b=0.75','rrf_k':60,'rrf_weights':[1,1],'lexical_k':20,'dedup':'NFC + prose whitespace; code/table structure exact; same revision/config; preserve per-source IDs/tokens'},'summary':summary,'cases':results,'fts_probe':fts}


if __name__=='__main__':
    import resource
    start_cpu=time.process_time();start=time.perf_counter()
    output=run(json.load(open(sys.argv[1])))
    output['resources']={'wall_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-start_cpu,'peak_rss_bytes_macos':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    with open(sys.argv[2],'w') as f:json.dump(output,f,ensure_ascii=False,indent=2)
    print(json.dumps({'summary':output['summary'],'fts_probe':output['fts_probe'],'resources':output['resources']},ensure_ascii=False,indent=2))

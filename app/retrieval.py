"""Pure ranking helpers. No database/model writes or query-specific rules."""
import collections
import math
import re
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
    if not corpus:return []
    words = set(tokens(query)); docs = [collections.Counter(tokens(h['text'])) for h in corpus]
    n = len(docs); avg = sum(sum(d.values()) for d in docs) / n or 1
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
        member={k:hit[k] for k in ['document_id','document_name','chunk_id','revision','sources','index_token','chunk_config_hash','risk','score','section','order','text']}
        if key in seen:
            result[seen[key]]['members'].append(member)
        else:
            seen[key]=len(result);result.append(dict(hit,members=[member]))
    return result

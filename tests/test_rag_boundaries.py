"""Offline evidence/dispatch boundaries. Fictional records, no real transport or models."""
from copy import deepcopy
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from app.rag_context import model_evidence
from app.rag import RagError,SYSTEM,config
from app.retrieval import bm25,fuse,groups
from test_rag import rig  # reuse the fictional per-test store/client fixture


@pytest.mark.parametrize('revoke_representative',[False,True])
def test_hybrid_dedup_sources_survive_rag_and_permission_recheck(rig,monkeypatch,revoke_representative):
    monkeypatch.setenv('P18_SEARCH_MODE','hybrid_dedup')
    for identifier in rig.chunks:
        rig.chunks[identifier]['text']='完全虚构项目负责人：林晓岚。'
    rig.grant(['a','b'])
    original=rig.service.search
    scoped=[]
    def search(query,top_k,document_filter=None):
        values=original(query,top_k,document_filter)['results']
        scoped.extend(h['document_id'] for h in values)
        hits=[dict(h,kind='text',chunk_config_hash='v3',table_structure_hash=None,score=.5,order=1) for h in values]
        result=groups(fuse(hits,bm25(query,hits)))
        assert len(result)==1 and len(result[0]['members'])==2
        # Simulate a grant change after scoped retrieval but before RAG assembly.
        if revoke_representative:rig.grant(['b'])
        return {'results':result}
    rig.service.search=search
    p=rig.rag.prepare('完全虚构项目负责人？')
    assert scoped==['a','b'] and len(p['evidence'])==1
    source=p['evidence'][0];members=source.get('members',[source])
    expected=['b'] if revoke_representative else ['a','b']
    assert [m['document_id'] for m in members]==expected
    for m in members:
        id=m['document_id']
        assert m['document_name']==rig.docs[id]['name']
        assert m['chunk_id']==rig.chunks[id]['id'] and m['revision']==1
        assert m['index_token']==rig.service.snapshot(id)['token']
        assert m['sources']==[{'block_id':'p1'}] and m['text']==rig.chunks[id]['text']
    rig.provider.reply={'status':'answered','answer':'林晓岚。[S1]','citations':['S1']}
    result=rig.rag.answer(p['ticket'],True)
    payload=json.loads(rig.provider.requests[0][1]['content'])
    assert payload['untrusted_evidence']==model_evidence(p['evidence'])
    assert result['citations']==[source]
    assert 'secret.docx' not in json.dumps(payload)
    if revoke_representative:assert 'a.docx' not in json.dumps(payload)


def install_ranked_fictional_documents(rig,texts):
    template=deepcopy(rig.docs['a'])
    rig.docs.clear();rig.chunks.clear()
    for n,text in enumerate(texts):
        identifier=f'g{n:02}'
        doc=deepcopy(template);doc.update(id=identifier,name=identifier+'.docx',sha256=identifier)
        doc['result']={'blocks':[{'text':text}]}
        rig.docs[identifier]=doc
        rig.chunks[identifier]={'id':'chunk-'+identifier,'document_id':identifier,'text':text}
    rig.grant(list(rig.docs))


def budget_for(question,source):
    return len(SYSTEM)+len(question)+len(json.dumps([],ensure_ascii=False))+256+len(json.dumps(source,ensure_ascii=False))


def test_default_eight_groups_can_omit_correct_ninth_group(rig,monkeypatch):
    monkeypatch.delenv('P18_RAG_EVIDENCE_COUNT',raising=False)
    monkeypatch.delenv('P18_RAG_CONTEXT_CHARS',raising=False)
    install_ranked_fictional_documents(rig,[f'完全虚构测试资料第{n}段，没有目标答案。' for n in range(8)]+['完全虚构目标：答案为蓝色。','完全虚构尾部内容。'])
    all_hits=rig.service.search('目标是什么？',20)['results']
    assert config()['evidence_count']==8 and len(all_hits)==10
    assert sum(len(json.dumps(h,ensure_ascii=False)) for h in all_hits)+len(SYSTEM)+500<20000
    p=rig.rag.prepare('目标是什么？')
    assert [s['chunk_id'] for s in p['evidence']]==[f'chunk-g{n:02}' for n in range(8)]
    assert [s['id'] for s in p['evidence']]==[f'S{n}' for n in range(1,9)]
    assert '答案为蓝色' not in json.dumps(p['evidence'],ensure_ascii=False)
    assert all_hits[8]['chunk_id']=='chunk-g08' # known omission, not a success assertion about recall
    assert not rig.provider.requests


def test_context_limit_skips_whole_oversized_answer_and_keeps_later_small_groups(rig,monkeypatch):
    monkeypatch.setenv('P18_RAG_CONTEXT_CHARS','2000')
    monkeypatch.delenv('P18_RAG_EVIDENCE_COUNT',raising=False)
    answer='完全虚构目标答案：蓝色。'+'完整结构必须保留。'*400
    install_ranked_fictional_documents(rig,['完全虚构简短说明。',answer,'完全虚构后续小片段。'])
    all_hits=rig.service.search('目标是什么？',20)['results']
    assert len(all_hits)<8 and len(answer)>2000
    p=rig.rag.prepare('目标是什么？')
    assert [s['chunk_id'] for s in p['evidence']]==['chunk-g00','chunk-g02']
    assert [s['text'] for s in p['evidence']]==[rig.chunks['g00']['text'],rig.chunks['g02']['text']]
    assert 'chunk-g01' not in json.dumps(p['evidence'])
    assert all_hits[1]['text']==answer and not rig.provider.requests


def test_context_budget_accumulation_can_omit_otherwise_fitting_answer(rig,monkeypatch):
    monkeypatch.setenv('P18_RAG_CONTEXT_CHARS','2000')
    install_ranked_fictional_documents(rig,['完全虚构第一段。'+'甲'*500,'完全虚构正确答案：蓝色。'+'乙'*500])
    question='目标是什么？';hits=rig.service.search(question,20)['results']
    # Every group fits alone, but both together exceed the real character budget.
    fields=['document_id','document_name','chunk_id','revision','index_token','text','section','sources','risk']
    sources=[{k:h[k] for k in fields} for h in hits]
    base=budget_for(question,{})-len('{}')
    costs=[len(json.dumps(s,ensure_ascii=False)) for s in sources]
    assert all(base+c<=2000 for c in costs) and base+sum(costs)>2000
    p=rig.rag.prepare(question)
    assert [s['chunk_id'] for s in p['evidence']]==['chunk-g00']
    assert 'chunk-g01' not in json.dumps(p['evidence']) and not rig.provider.requests


def test_all_oversized_groups_produce_no_evidence_without_provider_call(rig,monkeypatch):
    monkeypatch.setenv('P18_RAG_CONTEXT_CHARS','2000')
    install_ranked_fictional_documents(rig,['虚构大段落。'*600])
    assert rig.rag.prepare('虚构问题？')['status']=='no_evidence'
    assert not rig.provider.requests


def test_revocation_after_last_check_before_mock_transport_is_not_atomic(rig):
    """Expose the current race, without claiming postvalidation prevents egress."""
    rig.grant(['a','b']);p=rig.rag.prepare('虚构负责人？')
    entered=threading.Event();release=threading.Event();captured=[]
    def gated_mock_transport(messages,cfg):
        # This callable begins after answer's last preflight check. Wait BEFORE
        # capturing bytes as if they were being transmitted; no network exists.
        entered.set();assert release.wait(5)
        captured.append(deepcopy(messages))
        return json.dumps({'status':'answered','answer':'林晓岚。[S2]','citations':['S2']})
    rig.provider.complete=gated_mock_transport
    with ThreadPoolExecutor(1) as pool:
        pending=pool.submit(rig.rag.answer,p['ticket'],True)
        try:
            assert entered.wait(2)
            rig.grant([]) # isolated fixture file only, independent of the service lock
        finally:release.set()
        with pytest.raises(RagError) as error:pending.result(timeout=2)
    assert error.value.code=='evidence_stale'
    assert len(captured)==1 and '林晓岚' in json.dumps(captured,ensure_ascii=False)
    assert not rig.rag.sessions[p['session_id']]['turns']

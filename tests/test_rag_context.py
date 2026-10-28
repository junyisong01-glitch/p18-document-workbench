"""Fictional packing regressions: no remote calls and no answer-keyword routing."""
from copy import deepcopy
import json

import pytest

from app.rag import RagError, RagService, config
from app.rag_context import evidence_groups, model_evidence
from test_rag import rig
from test_rag_boundaries import install_ranked_fictional_documents


def metadata_heavy_search(rig):
    original = rig.service.search
    def search(*args, **kwargs):
        result = original(*args, **kwargs)
        for hit in result['results']:
            hit['sources'] = [dict(block_id='page-1', page=1, variant='original',
                                   label='物理第1页', raw_start=i*20, raw_end=i*20+19)
                              for i in range(45)]
            hit.update(kind='text', chunk_config_hash='fictional-config', table_structure_hash=None)
        return result
    rig.service.search = search


def prepare(rig, path, question):
    if path == 'prepare':
        return rig.rag.prepare(question)
    draft = rig.rag.draft(question)
    return rig.rag.selection(draft['draft_id'], 0, draft['default_candidate_ids'])


@pytest.mark.parametrize('path', ['prepare', 'selection'])
def test_coordinates_do_not_starve_complete_answer_and_preview_matches_dispatch(rig, path):
    answer = '5. Verification classes\n- Atlas: checks startup.\n- Boreal: checks behavior.\n- Cygnus: checks changes.'
    # Irrelevant, duplicated introductions have expensive source metadata. Old
    # packing exceeds 20k before reaching the complete third unique passage.
    install_ranked_fictional_documents(rig, ['Purpose: fictional verification plan.']*2 +
        ['Project overview: entirely fictional.'] + [answer]*2 + ['Other fictional content.'])
    metadata_heavy_search(rig)
    hits = rig.service.search('验证方案规定了哪些类别及用途？', 20)['results']
    old = [dict(h, id=f'S{i+1}') for i,h in enumerate(hits[:4])]
    assert len(json.dumps(old, ensure_ascii=False)) > 20000
    p = prepare(rig, path, '验证方案规定了哪些类别及用途？')
    target = next(s for s in p['evidence'] if s['text'] == answer)
    assert len(target['members']) == 2
    assert len(p['evidence']) == 4 and not rig.provider.requests
    assert all(len(m['sources']) == 45 for m in target['members'])
    payload = json.loads(rig.rag.tickets[p['ticket']]['messages'][1]['content'])
    wire_target = next(s for s in payload['untrusted_evidence'] if s['id'] == target['id'])
    assert wire_target['text'] == answer
    assert wire_target['members'] == [{k:v for k,v in m.items() if k not in {'sources', 'text'}} for m in target['members']]
    assert all('sources' not in s for s in payload['untrusted_evidence'])
    assert 'raw_start' not in json.dumps(payload)
    expected = deepcopy(rig.rag.tickets[p['ticket']]['messages'])
    assert RagService.selection_budget(p['question'],p['history'],p['evidence'],config())['message_chars'] == len(json.dumps(expected,ensure_ascii=False))
    with pytest.raises(RagError) as err:
        rig.rag.answer(p['ticket'],False)
    assert err.value.code == 'consent_required' and not rig.provider.requests
    rig.provider.reply = {'status':'answered','answer':f'Atlas、Boreal、Cygnus。[{target["id"]}]','citations':[target['id']]}
    result = rig.rag.answer(p['ticket'],True)
    assert rig.provider.requests == [expected]
    assert result['citations'] == [target]  # full, genuine locators stay available


@pytest.mark.parametrize('path', ['prepare', 'selection'])
def test_repeated_files_no_longer_consume_eight_default_slots(rig, path):
    install_ranked_fictional_documents(rig, ['Fictional document introduction.']*8 +
        ['Retention: keep fictional logs for 17 days.'])
    p = prepare(rig,path,'日志保留多久？')
    assert len(p['evidence']) == 2
    assert len(p['evidence'][0]['members']) == 8
    assert p['evidence'][1]['text'] == rig.chunks['g08']['text']
    assert len({m['chunk_id'] for m in p['evidence'][0]['members']}) == 8


@pytest.mark.parametrize('path', ['prepare', 'selection'])
@pytest.mark.parametrize('upstream_grouped', [False, True])
def test_long_duplicate_body_fits_once_with_all_sources_and_exact_dispatch(rig, monkeypatch, path, upstream_grouped):
    from app.rag import SYSTEM
    from app.retrieval import groups

    monkeypatch.setenv('P18_RAG_CONTEXT_CHARS', '20000')
    monkeypatch.setenv('P18_RAG_EVIDENCE_COUNT', '8')
    body = '虚构验收内容。' * 857  # 5,999 characters, repeated across three sources.
    install_ranked_fictional_documents(rig, [body] * 3)
    original = rig.service.search
    def search(*args, **kwargs):
        result = original(*args, **kwargs)
        hits = [dict(hit, kind='text', chunk_config_hash='fictional-config',
                     table_structure_hash=None, score=.5, order=n,
                     risk={'incomplete':bool(n), 'issues':[f'fictional warning {n}']})
                for n, hit in enumerate(result['results'])]
        result['results'] = groups(hits) if upstream_grouped else hits
        return result
    rig.service.search = search

    p = prepare(rig, path, '虚构验收要求是什么？')
    assert p['status'] == 'prepared' and len(p['evidence']) == 1
    full = deepcopy(p['evidence'])
    assert len(full[0]['members']) == 3
    assert [m['document_id'] for m in full[0]['members']] == list(rig.docs)
    assert all(m['text'] == body and m['sources'] for m in full[0]['members'])
    expected = deepcopy(rig.rag.tickets[p['ticket']]['messages'])
    wire = json.loads(expected[1]['content'])['untrusted_evidence'][0]
    assert wire['text'] == body
    assert wire['members'] == [{k:v for k,v in m.items() if k not in {'text', 'sources'}}
                               for m in full[0]['members']]
    assert expected[1]['content'].count(body) == 1
    budget = RagService.selection_budget(p['question'], p['history'], p['evidence'], config())
    assert budget['message_chars'] == len(json.dumps(expected, ensure_ascii=False)) < 20000
    if path == 'selection':
        assert p['budget'] == budget and p['messages'] == expected

    # Reproduce the previous projection, which dropped locators but repeated text.
    legacy = deepcopy(full)
    for item in [legacy[0]] + legacy[0]['members']:
        item.pop('sources')
    old_messages = [{'role':'system', 'content':SYSTEM}, {'role':'user', 'content':json.dumps({
        'question':p['question'], 'history_for_reference_only':p['history'],
        'untrusted_evidence':legacy}, ensure_ascii=False)}]
    assert len(json.dumps(old_messages, ensure_ascii=False)) > 20000
    with pytest.raises(RagError) as err:
        rig.rag.answer(p['ticket'], False)
    assert err.value.code == 'consent_required' and not rig.provider.requests
    rig.provider.reply = {'status':'answered', 'answer':'虚构验收内容。[S1]', 'citations':['S1']}
    result = rig.rag.answer(p['ticket'], True)
    assert rig.provider.requests == [expected]
    assert result['citations'] == full == p['evidence']


@pytest.mark.parametrize('path', ['prepare', 'selection'])
@pytest.mark.parametrize('change', ['revoke', 'revision', 'delete', 'index'])
def test_duplicate_member_stays_bound_to_permission_and_version(rig, path, change):
    for key in ['a','b']:
        rig.chunks[key]['text'] = 'Fictional retention: 17 days.'
    rig.grant(['a','b']);p=prepare(rig,path,'日志保留多久？')
    assert len(p['evidence']) == 1 and len(p['evidence'][0]['members']) == 2
    if change == 'revoke':rig.grant(['a'])
    elif change == 'revision':rig.docs['b']['revision'] += 1
    elif change == 'delete':rig.docs['b']['state'] = 'deleted'
    else:rig.service.current_config=lambda:False
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    assert not rig.provider.requests


def test_authorized_and_local_duplicates_remain_separate(rig):
    for key in rig.chunks:rig.chunks[key]['text']='Fictional shared body.'
    rig.grant(['b']);d=rig.rag.draft('虚构说明？')
    local=[c for c in d['candidates'] if not c['selectable']]
    assert local and all(not c['default_selected'] for c in local)
    p=rig.rag.selection(d['draft_id'],0,d['default_candidate_ids'])
    assert [s['document_id'] for s in p['evidence']] == ['b']
    assert 'secret' not in json.dumps(p['messages']) and 'a.docx' not in json.dumps(p['messages'])
    with pytest.raises(RagError) as err:
        rig.rag.selection(d['draft_id'],1,[local[0]['candidate_id']])
    assert err.value.code=='selection_forbidden'
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    assert not rig.provider.requests


@pytest.mark.parametrize('field,value', [('kind','code'), ('revision',2), ('chunk_config_hash','different'), ('table_structure_hash','different')])
def test_dedup_keeps_structural_and_version_boundaries(field,value):
    hit={'document_id':'fictional-a','chunk_id':'one','revision':1,'index_token':'one',
         'kind':'text','chunk_config_hash':'v3','table_structure_hash':None,'text':'  A  B  '}
    other=dict(hit,document_id='fictional-b',chunk_id='two',index_token='two')
    other[field]=value
    assert len(evidence_groups([hit,other]))==2
    assert 'members' not in hit  # input untouched


def test_dedup_does_not_merge_similar_values_or_code_indentation():
    base={'document_id':'a','chunk_id':'a','revision':1,'index_token':'a','kind':'text','text':'Retention: 17 days.'}
    different=dict(base,document_id='b',chunk_id='b',text='Retention: 71 days.')
    assert len(evidence_groups([base,different]))==2
    code=dict(base,kind='code',text='  return value')
    other=dict(code,document_id='b',chunk_id='b',text='return value')
    assert len(evidence_groups([code,other]))==2


def test_model_projection_does_not_mutate_full_sources_or_drop_text_and_risks():
    full=[{'id':'S1','text':'Fictional full body.','sources':[{'page':1,'raw_start':7}],
           'risk':{'incomplete':True,'issues':['fictional warning']},
           'members':[{'document_id':'x','text':'Fictional member body.','revision':2,
                       'index_token':'bound','sources':[{'block_id':'paragraph-1'}]}]}]
    before=deepcopy(full);wire=model_evidence(full)
    assert full==before and wire[0]['text']==full[0]['text'] and wire[0]['risk']==full[0]['risk']
    assert wire[0]['members'][0]=={k:v for k,v in full[0]['members'][0].items() if k!='sources'}


@pytest.mark.parametrize('different_text', [
    'Fictional different body.',
    ' Fictional shared body. ',
    'Fictional\nshared body.',
    'Fictional  shared body.',
])
def test_model_projection_preserves_every_member_text_when_group_texts_differ(different_text):
    full = [{'id':'S1', 'text':'Fictional shared body.', 'members':[
        {'document_id':'a', 'text':'Fictional shared body.'},
        {'document_id':'b', 'text':different_text}]}]
    assert model_evidence(full) == full


@pytest.mark.parametrize('copies', [1, 3])
@pytest.mark.parametrize('question,paragraph,reply', [
    ('测试计划包含哪三种主要测试类型？',
     '5. Test Types\nSmoke: basic sanity checks.\nFunctional: expected behavior.\nRegression: rerun after fixes.',
     {'status':'answered','answer':'冒烟检查主要流程，功能检查预期行为，回归复测修复后的功能。[S1]','citations':['S1']}),
    ('根据Verification Plan第5节，列出测试类型及用途。',
     '5. Test Types\nSmoke: basic sanity checks.\nFunctional: expected behavior.\nRegression: rerun after fixes.',
     {'status':'answered','answer':'Smoke检查主要流程；Functional检查预期行为；Regression在修复后复测。[S1]','citations':['S1']}),
    ('发布后允许回滚的时间窗口是多久？',
     'Rollback window: 36 hours after release.',
     {'status':'answered','answer':'发布后36小时。[S1]','citations':['S1']}),
    ('项目负责人的家庭住址是什么？',
     'Fictional project owner: Role Alpha. No home address is specified.',
     {'status':'insufficient_evidence','answer':'资料里没有住址信息。','citations':[]}),
])
def test_real_client_wire_and_answer_validation_with_offline_http_fixture(rig,monkeypatch,copies,question,paragraph,reply):
    """Declared fixture responses test transport/validation, NOT model reasoning.

    Local Qwen retrieval quality is measured separately in the isolated browser
    acceptance. Never add response routing or answer words to business retrieval.
    """
    from app.rag import DeepSeekClient, UNKNOWN
    monkeypatch.setenv('DEEPSEEK_API_KEY','fictional-offline-test-value')
    rig.chunks['b']['text'] = paragraph
    authorized = ['b']
    for n in range(1, copies):
        identifier = f'duplicate-{n}'
        rig.docs[identifier] = dict(deepcopy(rig.docs['b']), id=identifier,
                                    name=identifier+'.docx', sha256=identifier)
        rig.chunks[identifier] = {'id':'chunk-'+identifier, 'document_id':identifier, 'text':paragraph}
        authorized.append(identifier)
    rig.grant(authorized)
    rig.rag.client=DeepSeekClient()
    draft=rig.rag.draft(question)
    p=rig.rag.selection(draft['draft_id'],0,draft['default_candidate_ids'])
    captured=[]
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,*args):
            return json.dumps({'choices':[{'finish_reason':'stop','message':{
                'content':json.dumps(reply,ensure_ascii=False)}}]}).encode()
    def transport(request,timeout):
        payload=json.loads(request.data)
        assert payload['messages']==p['messages']
        wire = json.loads(payload['messages'][1]['content'])['untrusted_evidence'][0]
        assert wire['text'] == paragraph
        if copies > 1:
            assert len(wire['members']) == copies
            assert all('text' not in member for member in wire['members'])
        assert request.full_url==p['request_endpoint']
        assert payload['stream'] is False and payload['thinking']=={'type':'disabled'}
        assert 'UNAUTHORIZED_PRIVATE' not in json.dumps(payload)
        captured.append(payload)
        return Response()
    monkeypatch.setattr('app.rag.secure_urlopen',transport)
    assert not captured
    result=rig.rag.answer(p['ticket'],True)
    assert len(captured)==1 and result['status']=='answered' and result['answer_status']==reply['status']
    if reply['status']=='insufficient_evidence':
        assert result['answer']==UNKNOWN and result['citations']==[]
    else:
        assert result['answer']==reply['answer']
        assert result['citations']==p['evidence']

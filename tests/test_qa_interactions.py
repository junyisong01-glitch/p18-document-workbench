"""D changes: fictional offline provider, real PDF geometry, temporary data only."""
from copy import deepcopy
import json
import pytest
import pymupdf as fitz
from app.rag import RagError
from app.qa_highlight import locate
from test_rag import rig
from test_rag_selection import select
from test_qa_sources import source_fixture
from test_workbench import client


def answer(rig,d):
    p=select(rig,d)
    rig.provider.reply={'status':'answered','answer':'虚构证据。[S1]','citations':['S1']}
    return rig.rag.answer(p['ticket'],True)


def test_regeneration_replaces_same_turn_without_duplicate_history(rig):
    rig.grant(['a','b'])
    d=rig.rag.draft('虚构负责人是谁？');first=answer(rig,d)
    sid=first['session_id'];tid=first['turn_id']
    d=rig.rag.draft('前端不能改写原问题',sid,tid)
    assert d['question']=='虚构负责人是谁？' and d['history']==[]
    p=select(rig,d);old=p['ticket']
    p2=rig.rag.selection(d['draft_id'],1,[d['default_candidate_ids'][0]])
    with pytest.raises(RagError):rig.rag.answer(old,True)
    second=rig.rag.answer(p2['ticket'],True)
    assert second['turn_id']==tid and len(rig.rag.sessions[sid]['turns'])==1
    follow=rig.rag.draft('那他是谁？',sid)
    assert len(follow['history'])==1
    assert len(rig.provider.requests)==2


def test_regeneration_uses_preceding_history_only_and_keeps_other_turns(rig):
    rig.grant(['b']);first=answer(rig,rig.rag.draft('虚构问题一？'))
    sid=first['session_id'];second=answer(rig,rig.rag.draft('虚构问题二？',sid))
    draft=rig.rag.draft('ignored',sid,second['turn_id'])
    assert [h['question'] for h in draft['history']]==['虚构问题一？']
    answer(rig,draft)
    assert [t['turn_id'] for t in rig.rag.sessions[sid]['turns']]==[first['turn_id'],second['turn_id']]


def test_regeneration_cannot_target_another_session(rig):
    rig.grant(['b']);one=answer(rig,rig.rag.draft('虚构问题一？'))
    other=rig.rag.draft('虚构问题二？')
    with pytest.raises(RagError) as e:rig.rag.draft('ignored',other['session_id'],one['turn_id'])
    assert e.value.code=='turn_expired' and len(rig.provider.requests)==1


def test_regeneration_still_requires_new_consent_and_permission(rig):
    rig.grant(['b']);one=answer(rig,rig.rag.draft('虚构问题？'))
    d=rig.rag.draft('ignored',one['session_id'],one['turn_id']);p=select(rig,d)
    with pytest.raises(RagError) as e:rig.rag.answer(p['ticket'],False)
    assert e.value.code=='consent_required'
    rig.grant([])
    with pytest.raises(RagError):rig.rag.answer(p['ticket'],True)
    assert len(rig.provider.requests)==1


def test_pdf_exact_geometry_and_conservative_fallback(tmp_path):
    path=tmp_path/'fictional.pdf';pdf=fitz.open();p=pdf.new_page();p.insert_text((50,70),'Fictional duration = 45');p.insert_text((50,100),'Repeated statement');p.insert_text((50,120),'Repeated statement');pdf.save(path);pdf.close()
    result=locate(path,'.pdf',{'text':'Fictional duration = 45','sources':[{'page':1}]})
    assert result['status']=='matched' and result['pages'][0]['page']==1
    assert all(0<=v<=1 for b in result['pages'][0]['rects'] for v in b)
    for ext,text,sources in [('.docx','Fictional duration = 45',[{'page':1}]),('.pdf','Repeated statement',[{'page':1}]),('.pdf','Fictional duration = 45',[{'label':'第1页'}]),('.pdf','Fictional duration = 45',[{'page':99}]),('.pdf','Does not exist',[{'page':1}])]:
        assert locate(path,ext,{'text':text,'sources':sources})['status']=='unavailable'


def test_highlight_endpoint_requires_current_source(source_fixture):
    c,d,ch,state,p=source_fixture
    ch.update(text='some fictional evidence',sources=[{'page':1}])
    url='/api/documents/'+d['id']+'/source/highlight'
    assert c.get(url,params=p).status_code==200
    state['current']=False
    assert c.get(url,params=p).status_code==409


def test_highlight_rejects_repeated_text_across_pages_and_handles_rotation(tmp_path):
    path=tmp_path/'rotated.pdf';pdf=fitz.open()
    p=pdf.new_page();p.insert_text((50,70),'Fictional unique parameter 45');p.insert_text((50,100),'Duplicated everywhere');p.set_rotation(90)
    p=pdf.new_page();p.insert_text((50,100),'Duplicated everywhere');pdf.save(path);pdf.close()
    assert locate(path,'.pdf',{'text':'Duplicated everywhere','sources':[{'page':1}]})['status']=='unavailable'
    result=locate(path,'.pdf',{'text':'Fictional unique parameter 45','sources':[{'page':1}]})
    assert result['status']=='matched' and result['pages'][0]['rects'][0][0]>.5


def test_reselect_older_round_preserves_bounded_conversation(rig):
    rig.grant(['b']);sid=None;first=None
    for i in range(5):
        result=answer(rig,rig.rag.draft(f'虚构问题{i}？',sid));sid=result['session_id'];first=first or result
    assert len(rig.rag.sessions[sid]['turns'])==3
    d=rig.rag.draft('ignored',sid,first['turn_id']);assert d['history']==[]
    again=answer(rig,d);assert again['turn_id']==first['turn_id']
    assert len(rig.rag.sessions[sid]['turns'])==3 and len(rig.rag.sessions[sid]['rounds'])==5


def test_regeneration_api_uses_server_question_and_turn_id(client,rig,monkeypatch):
    from app import main
    from test_workbench import HEADERS
    monkeypatch.setattr(main,'RAG_SERVICE',rig.rag);rig.grant(['b'])
    def generate(payload):
        d=client.post('/api/rag/drafts',json=payload,headers=HEADERS).json()
        p=client.post('/api/rag/selection',json={'draft_id':d['draft_id'],'selection_version':0,'candidate_ids':d['default_candidate_ids']},headers=HEADERS).json()
        rig.provider.reply={'status':'answered','answer':'虚构事实[S1]','citations':['S1']}
        return client.post('/api/rag/answer',json={'ticket':p['ticket'],'consent':True},headers=HEADERS).json()
    first=generate({'question':'虚构问题？'})
    second=generate({'question':'不能改写','session_id':first['session_id'],'turn_id':first['turn_id']})
    assert first['turn_id']==second['turn_id'] and len(rig.rag.sessions[first['session_id']]['turns'])==1
    assert json.loads(rig.provider.requests[-1][-1]['content'])['question']=='虚构问题？'

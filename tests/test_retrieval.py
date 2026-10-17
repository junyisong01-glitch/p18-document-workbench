"""Pure ranking invariants; no model/vector fixtures or production databases."""
from copy import deepcopy
import pytest
from app.retrieval import bm25, fuse, groups, tokens


def hit(identifier, text, **changes):
    return dict(chunk_id=identifier,document_id=identifier,document_name=identifier,text=text,
                revision=1,index_token=identifier,sources=[{'block_id':identifier}],chunk_config_hash='v3',
                table_structure_hash=None,kind='text',risk={'incomplete':False},score=.3,section='正文',order=1,**changes)


def test_general_terms_and_rank_fusion():
    a=hit('a','接口请求超时');b=hit('b','duration integer 必填')
    assert {'负责','责人'}<=set(tokens('项目负责人'))
    assert 'device_id' in tokens('device_id string')
    assert bm25('duration',[a,b])[0]['chunk_id']=='b'
    assert bm25('无匹配内容',[])==[]
    result=fuse([a,b],[b]);assert result[0]['chunk_id']=='b'
    assert result[0]['score']==.3 # cosine is never added to lexical score
    assert result[0]['fusion_score']==pytest.approx(1/62+1/61)


def test_duplicate_members_keep_each_source_and_risk():
    a=hit('a','相同正文');b=hit('b','  相同正文  ');b['risk']['incomplete']=True
    result=groups([a,b]);assert len(result)==1
    assert {m['document_id'] for m in result[0]['members']}=={'a','b'}
    assert result[0]['members'][1]['risk']['incomplete']
    assert result[0]['members'][1]['index_token']=='b'


@pytest.mark.parametrize('change',[{'revision':2},{'chunk_config_hash':'v4'},{'text':'其他内容'},{'text':'x²'},{'kind':'code'},{'table_structure_hash':'different'}])
def test_unsafe_duplicates_not_merged(change):
    a=hit('a','x2');b=hit('b','x2');b.update(change)
    assert len(groups([a,b]))==2


def test_code_indent_and_table_layout_not_normalized():
    a=hit('a','if x:\n    f()');a['kind']='code';b=deepcopy(a);b['text']='if x:\nf()'
    assert len(groups([a,b]))==2
    a['kind']=b['kind']='table';a['text']='a\tb';b['text']='a b'
    assert len(groups([a,b]))==2


def test_vector_fallback_independent_of_hybrid_candidate_config(monkeypatch):
    import threading
    from types import SimpleNamespace
    from app.semantic import IndexService, SemanticError
    service=IndexService.__new__(IndexService)
    service.store=SimpleNamespace(LOCK=threading.RLock())
    service.current_config=lambda:True
    service.candidates=lambda identifier:{}
    monkeypatch.setenv('P18_SEARCH_CANDIDATES','invalid')
    assert service.search('query',mode='vector')['status']=='no_index'
    with pytest.raises(SemanticError,match='候选数量'):
        service.search('query',mode='hybrid')

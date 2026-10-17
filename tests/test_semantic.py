"""Real-model tests are opt-in; never substitute fabricated embeddings."""
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

import pytest
import pymupdf as fitz
from fastapi.testclient import TestClient

pytest.importorskip('qdrant_client', reason='安装 requirements-semantic.txt 后验证本地向量后端')

from app import main
from app.embedding import EmbeddingError, LocalQwen, settings
from test_workbench import HEADERS, client, upload, wait
from test_chunking import wait_chunks


def test_semantic_disabled_is_explicit(client):
    assert client.get('/api/semantic').json()['external_inference'] is False
    response = client.post('/api/search', headers=HEADERS, json={'query': '安装说明'})
    assert response.status_code == 503 and response.json()['detail']['code'] == 'model_unavailable'
    assert client.post('/api/search', headers=HEADERS, json={'query':'x', 'top_k':51}).status_code == 422
    assert client.post('/api/search', headers=HEADERS, json={'query':'x', 'top_k':1.5}).status_code == 422


@pytest.mark.parametrize('key,value', [('P18_EMBEDDING_DIMENSION','0'), ('P18_EMBEDDING_REVISION','main'), ('P18_EMBEDDING_MAX_TOKENS','32')])
def test_model_config_rejects_unsafe_parameters(monkeypatch, key, value):
    monkeypatch.setenv(key,value)
    with pytest.raises(ValueError):
        settings()


def test_embedding_timeout_stops_worker():
    # Exercise only the failure path; no fake model or vector is returned.
    provider = LocalQwen()
    class SilentPipe:
        def poll(self, timeout): return False
        def close(self): pass
    provider.pipe = SilentPipe()
    with pytest.raises(EmbeddingError, match='超时') as error:
        provider._receive()
    assert error.value.code == 'embedding_timeout' and provider.pipe is None


SAMPLES = [
    ('支付排障.pdf', '支付接口故障排查', '付款请求长时间没有响应时，应检查网络连接和第三方接口地址，将请求超时阈值由3秒调整到10秒，并记录请求日志和失败重试记录。'),
    ('退款规则.pdf', '订单退款处理', '客户取消已支付订单时，先核对交易状态，通过原支付渠道退回款项，记录退款流水号。退款需要财务复核，不能重复发起。'),
    ('设备预约.pdf', '实验设备预约', '预约实验设备必须提供设备编号与使用时长，每次预约不得超过120分钟。预约冲突时需要更换时段。'),
    ('部署回滚.pdf', '生产发布回滚', '新版本上线后错误率升高，应停止继续发布并回退到上一稳定版本。回滚前保留日志和数据库备份，随后执行健康检查。'),
    ('账号权限.pdf', '人员离职权限处理', '员工离职时应立即停用账号，撤销代码仓库、服务器及内部文档访问权限，并交接负责的工作。'),
    ('数据库备份.pdf', '数据库恢复流程', '数据库每日执行全量备份并加密存储，误删业务记录时，应先恢复备份到隔离环境，验证完整性后再恢复生产数据。'),
]
QUERIES = [
    ('付钱的时候一直转圈没有返回，怎么排查？', '支付排障.pdf'),
    ('买家不想要已经付款的商品，款项怎么退？', '退款规则.pdf'),
    ('仪器最多能借用多长时间？', '设备预约.pdf'),
    ('更新程序以后故障变多，怎样恢复之前的版本？', '部署回滚.pdf'),
    ('同事不再任职了，需要取消哪些系统访问？', '账号权限.pdf'),
    ('不小心删除了数据，有什么恢复办法？', '数据库备份.pdf'),
]


def research_pdf(title, text):
    doc = fitz.open(); page = doc.new_page()
    page.insert_textbox(fitz.Rect(40,40,550,780), title+'\n\n'+text, fontname='china-s', fontsize=12)
    value = doc.tobytes(); doc.close()
    return value


def wait_index(client, identifier, expected='complete'):
    for _ in range(1200):
        value = client.get(f'/api/documents/{identifier}/index').json()
        if value['status'] not in {'waiting','building','not_started','blocked'}:
            assert value['status'] == expected, value
            return value
        time.sleep(.05)
    raise AssertionError('index timed out')


@pytest.mark.skipif(os.environ.get('P18_TEST_LOCAL_EMBEDDINGS') != '1', reason='需要下载指定Qwen权重，显式启用真实模型验收')
def test_real_model_semantic_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv('P18_SEMANTIC_ENABLED','1')
    monkeypatch.setattr(main,'DATA',tmp_path)
    monkeypatch.setattr(main,'DB',tmp_path/'test.sqlite3')
    evidence = {'queries': [], 'checks': []}
    with TestClient(main.app) as c:
        assert c.get('/api/semantic').json()['enabled'] is True
        docs = {}
        for name,title,text in SAMPLES:
            d = wait(c, upload(c,name=name,data=research_pdf(title,text))['id'])
            assert d['state'] == 'ready'
            wait_chunks(c,d['id']); wait_index(c,d['id'])
            docs[name]=d
        for question, expected in QUERIES:
            started = time.perf_counter()
            response = c.post('/api/search',headers=HEADERS,json={'query':question})
            assert response.status_code == 200,response.text
            result = response.json()
            evidence['queries'].append({'query':question,'target':expected,'seconds':time.perf_counter()-started,'results':result['results']})
            assert len(result['results'])==5 and expected in [r['document_name'] for r in result['results']]
            assert all(r['sources'][0]['page']==1 and r['score']==pytest.approx(float(r['score'])) for r in result['results'])
        assert len({r['document_id'] for r in evidence['queries'][0]['results']}) > 1
        service=main.INDEX_SERVICE
        vector_count=service.client.count(service.collection).count
        for mode in ('hybrid','hybrid_dedup'):
            result=c.post('/api/search',headers=HEADERS,json={'query':'付款没有响应如何处理','mode':mode}).json()
            assert result['retrieval_mode']==mode and result['candidate_k']==20
            assert docs['支付排障.pdf']['id'] in {h['document_id'] for h in result['results']}
            assert all('fusion_score' in h and isinstance(h['score'],float) for h in result['results'])
            scoped=c.post('/api/search',headers=HEADERS,json={'query':'支付','mode':mode,'document_id':docs['支付排障.pdf']['id']}).json()
            assert scoped['results'] and all(h['document_id']==docs['支付排障.pdf']['id'] for h in scoped['results'])
        assert service.client.count(service.collection).count==vector_count
        with monkeypatch.context() as m:
            m.setenv('P18_SEARCH_MODE','hybrid_dedup')
            assert c.post('/api/search',headers=HEADERS,json={'query':'退款'}).json()['retrieval_mode']=='hybrid_dedup'
            assert c.post('/api/search',headers=HEADERS,json={'query':'退款','mode':'vector'}).json()['retrieval_mode']=='vector'
        assert c.post('/api/search',headers=HEADERS,json={'query':'x','mode':'invalid'}).status_code==422
        target=docs['支付排障.pdf']; route=f"/api/documents/{target['id']}/index"
        response=c.post('/api/search',headers=HEADERS,json={'query':QUERIES[0][0],'document_id':target['id'],'top_k':5})
        assert response.json()['results'] and all(r['document_id']==target['id'] for r in response.json()['results'])
        run=c.get(route).json(); c.post(route,headers=HEADERS,json={'revision':target['revision']})
        assert c.get(route).json()['generation']==run['generation']
        service=main.INDEX_SERVICE
        assert service.client.count(service.collection, count_filter=service.models.Filter(must=[
            service.models.FieldCondition(key='document_id',match=service.models.MatchValue(value=target['id']))])).count==1
        evidence['checks']+=['synonyms_top5','whole_library','document_scope','source_page','idempotent_build']
        # Independent sample enters real review policy; old index is immediately hidden.
        with main.LOCK:
            held=main.get(target['id']);held.update(state='review',quality='review')
            held['result']['issues']=[{'kind':'table','message':'独立样例复核测试','page':1}]
            main.save(held)
        assert not c.get(route).json()['searchable']
        assert not c.post('/api/search',headers=HEADERS,json={'query':QUERIES[0][0],'document_id':target['id']}).json()['results']
        assert c.post(route,headers=HEADERS,json={'revision':1}).status_code==409
        evidence['checks'].append('review_blocked')
        # Restore only by the normal review endpoint on fictional data.
        r=c.post(f"/api/documents/{target['id']}/review",headers=HEADERS,json={
            'action':'accept','revision':1,'reviewer':'独立自动化样例','checks':{'structure_correct':True}})
        assert r.status_code==200,r.text
        wait_chunks(c,target['id']);wait_index(c,target['id'])
        # A genuine new parsing revision must not retrieve old chunk IDs.
        old={p['chunk_id'] for p in c.post('/api/search',headers=HEADERS,json={'query':QUERIES[0][0],'document_id':target['id']}).json()['results']}
        r=c.post(f"/api/documents/{target['id']}/reparse",headers=HEADERS,json={'revision':1});assert r.status_code==200
        assert c.get(route).json()['searchable'] is False
        wait(c,target['id']);wait_chunks(c,target['id']);wait_index(c,target['id'])
        new=c.post('/api/search',headers=HEADERS,json={'query':QUERIES[0][0],'document_id':target['id']}).json()['results']
        assert new and not old.intersection(p['chunk_id'] for p in new)
        evidence['checks'].append('reparse_invalidates')
        # Real model unavailable/timeout failure paths never return invented results.
        from app.semantic import SemanticError
        service=main.INDEX_SERVICE
        with patch.object(service.provider,'encode',side_effect=EmbeddingError('model_unavailable','独立故障注入：模型不可用')):
            assert c.post('/api/search',headers=HEADERS,json={'query':'test'}).status_code==503
        with monkeypatch.context() as m:
            m.setenv('P18_EMBEDDING_DIMENSION','512')
            assert c.get(route).json()['status']=='stale'
            assert c.post('/api/search',headers=HEADERS,json={'query':'test'}).status_code==503
        with monkeypatch.context() as m:
            m.setenv('P18_CHUNK_TARGET','800')
            assert c.get(route).json()['status']=='stale'
            assert not c.post('/api/search',headers=HEADERS,json={'query':'test','document_id':target['id']}).json()['results']
        with monkeypatch.context() as m:
            m.setenv('P18_SEARCH_TOP_K','3')
            assert len(c.post('/api/search',headers=HEADERS,json={'query':QUERIES[0][0]}).json()['results'])==3
        evidence['checks']+=['model_failure_no_fallback','config_change_stale','chunk_config_stale','developer_top_k']
        # Build failures are independent of successful chunk preparation.
        with patch.object(service.client,'upsert',side_effect=RuntimeError('isolated write failure')):
            failure_doc=wait(c,upload(c,name='独立故障样例.pdf',data=research_pdf('故障注入验证','仅用于验证索引写入错误处理，不用于企业资料。'))['id'])
            failed=wait_index(c,failure_doc['id'],'failed')
            assert failed['error_code']=='index_write_failed'
            assert c.get(f"/api/documents/{failure_doc['id']}/chunks").json()['status']=='complete'
        r=c.post(f"/api/documents/{failure_doc['id']}/index",headers=HEADERS,json={'revision':1})
        assert r.status_code==200;wait_index(c,failure_doc['id'])
        evidence['checks'].append('index_write_failure_and_retry')
        # Change admission after the genuine vector query but before returning.
        original_query=service.client.query_points
        def revoke_after_query(*args,**kwargs):
            result=original_query(*args,**kwargs)
            with main.LOCK:
                doc=main.get(failure_doc['id']);doc['state']='held';main.save(doc)
            return result
        with patch.object(service.client,'query_points',side_effect=revoke_after_query):
            result=c.post('/api/search',headers=HEADERS,json={'query':'故障验证','document_id':failure_doc['id'],'mode':'hybrid_dedup'}).json()
            assert not result['results']
        evidence['checks'].append('final_sqlite_revalidation')
        with pytest.raises(EmbeddingError) as long_error:
            service.provider.encode(['long text ' * 5000])
        assert long_error.value.code=='input_too_long'
        evidence['checks'].append('long_input_no_silent_truncation')
        with patch.object(service.provider,'encode',side_effect=EmbeddingError('embedding_timeout','独立故障注入：超时')):
            timed=wait(c,upload(c,name='超时样例.pdf',data=research_pdf('超时验证','仅用于验证向量任务超时后明确记录原因。'))['id'])
            timeout_run=wait_index(c,timed['id'],'failed')
            assert timeout_run['error_code']=='embedding_timeout'
        evidence['checks'].append('build_timeout_classification')
        old_reservation=docs['设备预约.pdf']
        replacement=wait(c,upload(c,name='设备预约.pdf',data=research_pdf('预约新版本','新版设备预约上限改为90分钟，需要登记设备编号。'),mode='replace',replace_id=old_reservation['id'])['id'])
        wait_index(c,replacement['id'])
        r=c.post('/api/search',headers=HEADERS,json={'query':'设备预约时长'})
        assert all(hit['document_id']!=old_reservation['id'] for hit in r.json()['results'])
        evidence['checks'].append('replacement_invalidates')
        evidence['model']=c.get('/api/semantic').json()
        keep=docs['退款规则.pdf']; before=c.get(f"/api/documents/{keep['id']}/index").json()
        interrupted=service.read(docs['部署回滚.pdf']['id']);interrupted['status']='building';service.write(interrupted)
    with TestClient(main.app) as c:
        after=wait_index(c,keep['id'])
        assert before['generation']==after['generation']
        assert c.post('/api/search',headers=HEADERS,json={'query':QUERIES[1][0],'document_id':keep['id']}).json()['results']
        evidence['checks'].append('restart_persists')
        recovered=wait_index(c,docs['部署回滚.pdf']['id'])
        assert recovered['generation']!=interrupted['generation']
        evidence['checks'].append('interrupted_build_recovery')
        assert c.delete(f"/api/documents/{keep['id']}",headers=HEADERS).status_code==200
        result=c.post('/api/search',headers=HEADERS,json={'query':QUERIES[1][0]}).json()
        assert all(r['document_id'] != keep['id'] for r in result['results'])
        evidence['checks'].append('delete_invalidates')
    monkeypatch.setenv('P18_EMBEDDING_DIMENSION','512')
    with TestClient(main.app) as c:
        rebuilt=wait_index(c,target['id'])
        assert rebuilt['model']['dimension']==512 and rebuilt['config_hash']!=run['config_hash']
        result=c.post('/api/search',headers=HEADERS,json={'query':QUERIES[0][0],'document_id':target['id']})
        assert result.status_code==200 and result.json()['results']
        evidence['checks'].append('new_model_config_rebuild')
    output=os.environ.get('P18_SEMANTIC_EVIDENCE')
    if output: Path(output).write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')

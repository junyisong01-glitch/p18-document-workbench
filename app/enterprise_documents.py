"""History search stays out of RAG. Corrections stage real source artifacts and
publish only after valid indexing, keeping the business version and old source.
"""
import json,time,uuid,io,hashlib
from dataclasses import replace
from fastapi import HTTPException,UploadFile,File,Form
from pydantic import BaseModel,ConfigDict,Field
from app import library_store
from app.business_review import review_reasons, technical_ready

class HistorySearch(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    query:str=Field(min_length=1,max_length=2000)
    top_k:int=Field(default=5,ge=1,le=20)

class ParagraphEdit(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    ordinal:int=Field(ge=0)
    text:str=Field(max_length=50000)

class Correction(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    expected:int=Field(ge=0)
    declaration:bool
    reason:str=Field(min_length=1,max_length=2000)
    paragraphs:list[ParagraphEdit]=Field(min_length=1,max_length=100)

def install_updates(store,central,user,read,manager,write,summary,visible):
    with store.connect()as c:
        c.execute('CREATE TABLE IF NOT EXISTS business_edits (document_id TEXT PRIMARY KEY,previous_id TEXT NOT NULL,previous_version INTEGER NOT NULL,editor TEXT NOT NULL,reason TEXT NOT NULL,declared_minor INTEGER NOT NULL,created REAL NOT NULL,completed REAL)')
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS business_one_pending_v2 ON business_documents(json_extract(body,'$.series')) WHERE json_extract(body,'$.status') IN ('submitted','approved','returned','correction_pending') AND json_extract(body,'$.deleted')=0")
    def eligible(doc,u):
        b=read(doc['id'])
        return bool(b and not b.get('deleted')and(b['status']=='legacy_archived'or b['status']=='published')and visible(doc,u)and store.business_raw_index_status(doc['id']).get('searchable'))
    @store.app.post('/api/business/history-search')
    def history_search(body:HistorySearch):
        if not body.query.strip():raise HTTPException(422,'问题不能为空')
        u=user();service=store.require_semantic()
        with store.LOCK:
            allowed={d['id']for d in store.all_docs()if eligible(d,u)}
        from app.embedding import EmbeddingError
        from app.semantic import SemanticError
        try:result=service.search(body.query.strip(),top_k=body.top_k,document_filter=lambda d:d['id']in allowed)
        except (EmbeddingError,SemanticError)as exc:raise HTTPException(503,{'code':exc.code,'message':str(exc)})from exc
        with store.LOCK:
            fresh={d['id']for d in store.all_docs()if eligible(d,u)}
            result['results']=[h for h in result.get('results',[])if all(m['document_id']in fresh for m in h.get('members',[h]))]
            for hit in result['results']:
                b=read(hit['document_id']);hit['historical']=bool(b['archived']or b['status']=='legacy_archived');hit['eligible_for_rag']=False
        result.update(scope='history_included',eligible_for_rag=False,message='高级查阅包含有权历史版本；此结果不能加入RAG。主搜索与问答仍仅使用当前发布且索引有效资料。')
        return result
    def assert_edit(identifier,expected=None):
        u=user();doc=store.get(identifier);b=read(identifier)
        if not b or not visible(doc,u)or b['owner']!=u['username']or u['role']=='guest':raise HTTPException(403,'仅上传者可勘误本人资料')
        if b['status']!='published'or b['archived']or b['deleted']:raise HTTPException(409,'仅可勘误当前已发布版本')
        if expected is not None and b['version']!=expected:raise HTTPException(409,'资料状态已变化，请刷新')
        return u,doc,b
    def original(doc):return store.folder_for(doc['id'])/('original'+doc['ext'])
    def editable(p):
        return not bool(p._p.xpath('.//w:drawing|.//w:pict|.//w:fldChar|.//w:instrText|.//w:hyperlink|.//w:object'))
    @store.app.get('/api/business/documents/{identifier}/editable')
    def editing_view(identifier:str):
        with store.LOCK:
            u,doc,b=assert_edit(identifier)
            if doc['ext']!='.docx':return {'expected':b['version'],'format':doc['ext'],'paragraphs':[],'notice':'此格式请上传同格式的勘误文件，通过检查前旧内容继续生效。'}
            from docx import Document
            paragraphs=[{'ordinal':i,'text':p.text,'editable':editable(p)}for i,p in enumerate(Document(original(doc)).paragraphs)if p.text]
            return {'expected':b['version'],'format':'.docx','paragraphs':paragraphs,'notice':'普通段落支持正文勘误；改动段落的局部字形可能重排。表格/复杂对象请上传修正版；勘误文件仍会执行解析和内容风险检查。'}
    async def stage(identifier,expected,reason,declaration,file):
        if declaration is not True or not reason.strip()or len(reason)>2000:raise HTTPException(422,'须声明为轻量勘误并说明原因；核心修改请上传新版本')
        with store.LOCK:
            u,doc,b=assert_edit(identifier,expected)
            if not(file.filename or'').lower().endswith(doc['ext']):raise HTTPException(422,'勘误原稿须保留文件格式，核心修改请走新版本')
            with store.connect()as c:
                pending=any(json.loads(r[0])['series']==b['series']and json.loads(r[0])['status']in {'submitted','approved','returned','correction_pending'}and not json.loads(r[0]).get('deleted')for r in c.execute('SELECT body FROM business_documents'))
            if pending:raise HTTPException(409,'已有待处理版本或勘误')
            # The native upload accepts a real source; parsed text is never patched alone.
            response=(await store.upload(files=[file],mode='keep',replace_id=''))[0]
            if response['status']!='accepted':raise HTTPException(409,response['message'])
            new_id=response['id'];new=store.get(new_id)
            try:
                with store.connect()as c:
                    latest=read(identifier,c)
                    if latest['version']!=expected:raise ValueError()
                    meta=library_store.read(c,identifier)[1]
                    library_store.write(c,new_id,meta,0)
                    target=dict(b,version=1,status='correction_pending',archived=False,deleted=False,company_public=False,legacy=False,replaces=identifier,correction=True,approved_by=u['username'])
                    if b.get('legacy'):
                        # Preserve the old explicit job ACL independently of the new source hash.
                        rule=store.business_legacy_acl.get(identifier,{})
                        if rule.get('roles')is not None:target['read_jobs']=[j for j in rule['roles']if not(rule.get('code')=='EXT-13'and j=='运维')]
                    c.execute('INSERT INTO business_documents VALUES (?,?)',(new_id,json.dumps(target,ensure_ascii=False)))
                    c.execute('INSERT INTO business_edits VALUES (?,?,?,?,?,?,?,NULL)',(new_id,identifier,expected,u['username'],reason,1,time.time()))
                    c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',(new_id,time.time(),u['username'],'minor_correction_declared',json.dumps({'previous_id':identifier,'reason':reason,'declared_minor':True,'previous_source_sha256':doc.get('sha256'),'source_sha256':new.get('sha256')},ensure_ascii=False)))
            except Exception:
                store.delete(new_id)
                raise HTTPException(409,'勘误提交冲突，原生效内容未改变')from None
            new=store.get(new_id)
            new['publication_rules']=1
            store.save(new)
            store.schedule_chunks(new)
            return {'document':summary(store.get(new_id)),'notice':'旧正文继续生效。普通勘误通过检查和索引后自动切换，命中内容风险时送审。'}
    @store.app.post('/api/business/documents/{identifier}/correction-file')
    async def correction_file(identifier:str,file:UploadFile=File(...),expected:int=Form(...),reason:str=Form(...),declaration:bool=Form(...)):
        return await stage(identifier,expected,reason,declaration,file)
    @store.app.post('/api/business/documents/{identifier}/correction')
    async def correction(identifier:str,body:Correction):
        with store.LOCK:
            u,doc,b=assert_edit(identifier,body.expected)
            if doc['ext']!='.docx':raise HTTPException(422,'此格式须上传修正原稿')
            from docx import Document
            document=Document(original(doc));seen=set();changed=False
            for change in body.paragraphs:
                if change.ordinal in seen or change.ordinal>=len(document.paragraphs):raise HTTPException(422,'段落身份无效')
                seen.add(change.ordinal);p=document.paragraphs[change.ordinal]
                if not editable(p):raise HTTPException(422,'此段含复杂对象，请上传修正原稿')
                changed=changed or p.text!=change.text
                p.text=change.text
            if not changed:raise HTTPException(409,'正文没有修改')
            buffer=io.BytesIO();document.save(buffer);buffer.seek(0)
            return await stage(identifier,body.expected,body.reason,body.declaration,UploadFile(filename='correction.docx',file=buffer))
    old_complete=getattr(store,'on_index_complete',lambda identifier:True)
    def complete(identifier):
        result=old_complete(identifier)
        with store.LOCK:
            b=read(identifier)
            if not b or b['status']!='correction_pending':return result
            doc=store.get(identifier)
            if not technical_ready(doc) or not store.business_raw_index_status(identifier).get('searchable'):
                return False
            if doc.get('publication_rules')==1 and review_reasons(doc,b):
                return True  # Index stays private while content is reviewed.
            with store.connect()as c:
                edit=c.execute('SELECT * FROM business_edits WHERE document_id=?',(identifier,)).fetchone()
                old=read(edit['previous_id'],c)if edit else None
                if not old or old['version']!=edit['previous_version']or old['status']!='published'or old['archived']or old['deleted']:
                    if not b.get('correction_error'):
                        b['correction_error']='原生效版本或授权已变化，未切换本次勘误；请取消后按最新版本重新提交。'
                        c.execute('UPDATE business_documents SET body=?WHERE document_id=?',(json.dumps(b,ensure_ascii=False),identifier))
                        c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',(identifier,time.time(),edit['editor']if edit else'background','minor_correction_conflict',json.dumps({'note':b['correction_error']},ensure_ascii=False)))
                    return False
                old.update(archived=True,version=old['version']+1)
                b.update(status='published',approved_fingerprint=store.fingerprint(doc),version=b['version']+1,
                         published_by=edit['editor'])
                # Public and explicit read grants continue for this logical same-version correction.
                b['company_public']=old.get('company_public',False)
                c.execute('UPDATE business_documents SET body=?WHERE document_id=?',(json.dumps(old,ensure_ascii=False),edit['previous_id']))
                c.execute('UPDATE business_documents SET body=?WHERE document_id=?',(json.dumps(b,ensure_ascii=False),identifier))
                c.execute('INSERT OR REPLACE INTO business_grants SELECT ?,username,expires FROM business_grants WHERE document_id=?',(identifier,edit['previous_id']))
                c.execute('UPDATE business_edits SET completed=?WHERE document_id=?',(time.time(),identifier))
                c.execute('INSERT INTO business_events(document_id,at,actor,action,body)VALUES(?,?,?,?,?)',(identifier,time.time(),edit['editor'],'minor_correction_activated',json.dumps({'previous_id':edit['previous_id'],'same_business_version':True})))
            return True
    store.on_index_complete=complete
    store.finalize_correction=complete

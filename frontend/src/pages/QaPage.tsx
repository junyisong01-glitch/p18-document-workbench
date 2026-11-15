import {useEffect,useState} from 'react'
import {PageHeader} from '@/components/bits'
import {DocPreviewDialog} from '@/components/DocView'
import {api} from '@/lib/api'
import {useSession} from '@/lib/session'
import type {Doc} from '@/lib/types'
export default function QaPage(){
 const {kbId,visibleDocs}=useSession()
 const [question,setQuestion]=useState(''),[draft,setDraft]=useState<any>(null),[selected,setSelected]=useState<string[]>([]),[version,setVersion]=useState(0),[pending,setPending]=useState<any>(null),[consent,setConsent]=useState(false),[answer,setAnswer]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[preview,setPreview]=useState<Doc|null>(null),[sourceRef,setSourceRef]=useState<any>(undefined)
 useEffect(()=>{setDraft(null);setPending(null);setAnswer(null);setSelected([]);setConsent(false)},[kbId])
 async function ask(e:React.FormEvent){e.preventDefault();setBusy(true);setError('');setPending(null);setAnswer(null);try{const d=await api.post<any>('/api/rag/drafts',{question});setDraft(d);setSelected(d.default_candidate_ids||[]);setVersion(d.selection_version||0);if(d.status!=='drafted')setError(d.message||'请补全问题')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function prepare(){setBusy(true);setError('');try{const p=await api.post<any>('/api/rag/selection',{draft_id:draft.draft_id,selection_version:version,candidate_ids:selected});setVersion(p.selection_version??version+1);setPending(p);setConsent(false)}catch(e){setPending(null);setError((e as Error).message)}finally{setBusy(false)}}
 async function send(){if(!pending||!consent||!pending.configured||busy)return;setBusy(true);setError('');try{setAnswer(await api.post<any>('/api/rag/answer',{ticket:pending.ticket,consent:true}));setPending(null)}catch(e){setPending(null);setError((e as Error).message)}finally{setBusy(false)}}
 const cls='rounded-md border border-border bg-card p-4'
 return <div className="space-y-5"><PageHeader kicker="Grounded Q&A" title="知识问答" desc={kbId==='qichen'?'启辰资料仅供本地查看，未获外发授权。':'人工选择获准证据，核对完整消息后再确认发送。'}/>
 <form onSubmit={ask} className="flex gap-3"><input aria-label="问答问题" className={cls+' flex-1'} value={question} onChange={e=>setQuestion(e.target.value)} maxLength={2000}/><button disabled={busy||!question.trim()} className={cls}>检索证据</button></form>
 {error&&<p role="alert">{error}</p>}
 {draft?.budget_skipped>0&&<p>有{draft.budget_skipped}组证据因容量未能默认装入，不能据此保证答案完整。</p>}
 {draft?.budget&&<p>容量上限：{draft.budget.group_limit}组；完整消息{draft.budget.context_limit}字符。实际容量由服务端检查。</p>}
 {draft?.candidates?.map((c:any)=><section className={cls} key={c.candidate_id}><label><input type="checkbox" disabled={busy||!c.selectable||kbId==='qichen'} checked={selected.includes(c.candidate_id)} onChange={e=>{setPending(null);setConsent(false);setSelected(e.target.checked?[...selected,c.candidate_id]:selected.filter(x=>x!==c.candidate_id))}}/> {c.evidence.document_name} · {c.selectable?'获准候选':c.permission_reason==='deployment_policy'?'本地可读，但部署策略禁止外发':'仅本地，尚无有效外发许可'}</label><pre className="mt-3 whitespace-pre-wrap text-sm">{c.evidence.text}</pre><button onClick={()=>{setSourceRef({revision:c.evidence.revision,index_token:c.evidence.index_token,chunk_id:c.evidence.chunk_id});setPreview(visibleDocs.find(d=>d.id===c.evidence.document_id)||null)}}>查看来源</button></section>)}
 {draft?.candidates&&kbId!=='qichen'&&<button className={cls} disabled={busy||!selected.length} onClick={prepare}>生成完整消息预览</button>}
 {pending&&<section role="dialog" aria-label="最终发送确认" className={cls+' space-y-4'}><h2>最终发送确认</h2><p>接收服务：{pending.provider}；模型：{pending.model}；地址：{pending.request_endpoint}</p><p>{pending.budget?.message_chars} / {pending.budget?.context_limit}字符</p><pre className="max-h-96 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify(pending.messages,null,2)}</pre>{!pending.configured&&<p>真实AI未启用。当前可核对消息，不能发送。</p>}<label><input type="checkbox" disabled={!pending.configured||busy} checked={consent} onChange={e=>setConsent(e.target.checked)}/>我已核对本次原文、来源和接收地址，同意本轮发送</label><button disabled={!consent||!pending.configured||busy} onClick={send}>确认发送</button></section>}
 {answer&&<section className={cls}><p>{answer.answer_status}</p><p className="whitespace-pre-wrap">{answer.answer}</p>{answer.citations?.map((c:any,i:number)=><button key={i} onClick={()=>{setSourceRef({revision:c.revision,index_token:c.index_token,chunk_id:c.chunk_id});setPreview(visibleDocs.find(d=>d.id===c.document_id)||null)}}>[{c.id||i+1}] {c.document_name}</button>)}<p>引用编号合法不等于事实正确，请核对原文。</p></section>}
 <DocPreviewDialog sourceRef={sourceRef} doc={preview} open={!!preview} onClose={()=>setPreview(null)}/>
 </div>
}

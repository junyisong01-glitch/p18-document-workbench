import type { Doc } from '../lib/types'
import { demoIdentityName } from '../lib/demo-identity-names'
import { StatusBadge } from './bits'
import './DocumentFacts.css'
import { previewDocumentLifecycle, type Lifecycle, type LifecycleEvent } from '../lib/document-lifecycle-preview'

type Event = LifecycleEvent
type Details = {created_at?:string|number;workflow?:{status:string;archived?:boolean;deleted?:boolean;restricted?:boolean;department?:string;legacy?:boolean};technical_index_ready?:boolean;lifecycle?:Lifecycle}
function date(value?:string|number, fallback='时间未留存') {
  if(value==null||value==='')return fallback
  const parsed=new Date(typeof value==='number'?value*1000:value)
  if(Number.isNaN(parsed.getTime()))return fallback
  return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(parsed)
}
function name(event?:Event|null){return event?.actor?(demoIdentityName(event.actor)||event.actor):'操作人未留存'}
export function DocumentFacts({doc,detail}:{doc:Doc;detail:Details}){
  const workflow=detail.workflow
  const {facts,simulated}=previewDocumentLifecycle(doc.code||doc.id,workflow?.department||doc.dept,!!workflow?.legacy,detail.lifecycle,typeof document!=='undefined'&&!!document.querySelector('.p18-preview-marker'))
  const published=workflow?.status==='published'&&!workflow.archived&&!workflow.deleted
  const status=workflow?.deleted?'已移入回收站':workflow?.archived?'历史归档':published?(detail.technical_index_ready?'已发布 · 可检索':'已发布 · 暂不可检索'):({submitted:'处理中',approved:'审核通过',returned:'已退回',withdrawn:'已撤回',correction_pending:'勘误处理中',taken_down:'已下架'}[workflow?.status||'']||'尚未发布')
  const imported=!!workflow?.legacy&&!facts?.submitted
  const reviewNote=workflow?.legacy?'历史审核记录未留存':facts?.published?.automatic?'系统检查后发布':workflow?.status==='approved'||facts?.published?'审核记录未留存':workflow?.status==='returned'?'已退回修改':workflow?.status==='withdrawn'?'提交已撤回':'尚未完成审核'
  const publicationNote=workflow?.deleted?'已移入回收站':workflow?.archived?'历史归档':workflow?.status==='taken_down'?'已下架':published?'已发布':'尚未发布'
  return <section className="document-facts" aria-label="文档信息">
    <div className="document-facts-badges">
      {workflow?<span className={`document-state ${published&&detail.technical_index_ready?'is-published':''}`}><i/>{status}</span>:<StatusBadge doc={doc}/>}
      {(workflow?.department||doc.dept)&&<span className="document-facts-tag">{workflow?.department||doc.dept}</span>}
      {(workflow?.restricted||doc.confidentiality==='机密')&&<span className="document-facts-tag is-restricted">机密</span>}
      <span className="document-facts-code">{doc.code&&<>编号 {doc.code}<b>·</b></>}版本 {doc.version}</span>
    </div>
    {simulated&&<p className="document-facts-demo">演示记录<span>以下姓名与时间为虚构展示数据</span></p>}
    <dl className="document-facts-grid">
      <div><dt>{imported?'资料来源':'上传者'}</dt><dd>{imported?'历史资料导入':facts?.submitted?name(facts.submitted):'上传信息未留存'}{imported&&<small>沿用原资料内容</small>}</dd></div>
      <div><dt>{imported?'入库登记时间':'提交时间'}</dt><dd>{date(imported?detail.created_at:facts?.submitted?.at)}{imported&&<small>本系统登记时间，非原始提交时间</small>}</dd></div>
      <div><dt>{facts?.reviewed?'审核人 / 时间':'审核情况'}</dt><dd>{facts?.reviewed?name(facts.reviewed):reviewNote}{facts?.reviewed&&<small>{date(facts.reviewed.at)}</small>}</dd></div>
      <div><dt>{facts?.published?'发布人 / 时间':'发布情况'}</dt><dd>{facts?.published?(facts.published.automatic?'系统自动发布':name(facts.published)):publicationNote}{facts?.published?<small>{date(facts.published.at)}</small>:published&&<small>历史发布人及时间未留存</small>}</dd></div>
    </dl>
  </section>
}

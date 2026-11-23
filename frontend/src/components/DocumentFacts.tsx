import type { Doc } from '../lib/types'
import { demoIdentityName } from '../lib/demo-identity-names'
import { StatusBadge } from './bits'
import './DocumentFacts.css'

type Event = {actor?:string;at?:string|number;automatic?:boolean}
type Details = {workflow?:{status:string;archived?:boolean;deleted?:boolean;restricted?:boolean;department?:string};technical_index_ready?:boolean;lifecycle?:{submitted?:Event;reviewed?:Event;published?:Event}}
function date(value?:string|number) {
  if(value==null||value==='')return '暂无记录'
  const parsed=new Date(typeof value==='number'?value*1000:value)
  if(Number.isNaN(parsed.getTime()))return '暂无记录'
  return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(parsed)
}
function name(event?:Event){return event?.actor?(demoIdentityName(event.actor)||event.actor):'暂无记录'}
export function DocumentFacts({doc,detail}:{doc:Doc;detail:Details}){
  const workflow=detail.workflow, facts=detail.lifecycle
  const published=workflow?.status==='published'&&!workflow.archived&&!workflow.deleted
  const status=workflow?.deleted?'已移入回收站':workflow?.archived?'历史归档':published?(detail.technical_index_ready?'已发布 · 可检索':'已发布 · 暂不可检索'):({submitted:'处理中',approved:'审核通过',returned:'已退回',withdrawn:'已撤回',correction_pending:'勘误处理中',taken_down:'已下架'}[workflow?.status||'']||'尚未发布')
  return <section className="document-facts" aria-label="文档信息">
    <div className="document-facts-badges">
      {workflow?<span className={`document-state ${published&&detail.technical_index_ready?'is-published':''}`}><i/>{status}</span>:<StatusBadge doc={doc}/>}
      {(workflow?.department||doc.dept)&&<span className="document-facts-tag">{workflow?.department||doc.dept}</span>}
      {(workflow?.restricted||doc.confidentiality==='机密')&&<span className="document-facts-tag is-restricted">机密</span>}
      <span className="document-facts-code">{doc.code&&<>编号 {doc.code}<b>·</b></>}版本 {doc.version}</span>
    </div>
    <dl className="document-facts-grid">
      <div><dt>上传者</dt><dd>{name(facts?.submitted)}</dd></div>
      <div><dt>提交时间</dt><dd>{date(facts?.submitted?.at)}</dd></div>
      <div><dt>审核人 / 时间</dt><dd>{name(facts?.reviewed)}{facts?.reviewed&&<small>{date(facts.reviewed.at)}</small>}</dd></div>
      <div><dt>发布人 / 时间</dt><dd>{facts?.published?.automatic?'系统自动发布':name(facts?.published)}{facts?.published&&<small>{date(facts.published.at)}</small>}</dd></div>
    </dl>
  </section>
}

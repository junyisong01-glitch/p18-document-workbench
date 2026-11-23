import {useState} from 'react'
import {SubmissionProgress} from './SubmissionProgress'
import {DocumentFormat,DocumentModal} from './DocumentLayout'
import {documentScope} from './BusinessDocumentTools'
import {DocumentRowActions} from './DocumentRowActions'
import type {BusinessRow} from './BusinessPresentation'
import {submissionLabel,submissionDate} from '../lib/document-workflow'
import {documentTitleParts} from '../lib/document-title'

export function MySubmissionRow({row,own,manage,boss,busy,preview,review,start,act,audit,correct,reupload}:{row:BusinessRow;own:boolean;manage:boolean;boss:boolean;busy:boolean;preview:()=>void;review:()=>void;start:(action:string)=>void;act:(action:string)=>void;audit:()=>void;correct:()=>void;reupload:()=>void}){
 const [details,setDetails]=useState(false),b=row.workflow,status=submissionLabel(row,manage)
 const problems=[...new Set([b.auto_publish_error,b.correction_error,row.technical_error,row.index_error,...row.parse_reasons||[]].filter(Boolean))]
 const terminal=['published','withdrawn','taken_down'].includes(b.status)||b.archived||b.deleted
 return <article data-document-id={row.id} className="dm-document-row dm-submission-row"><div className="dm-row-main"><DocumentFormat format={row.format}/><div className="dm-row-copy"><div className="dm-title-line"><button type="button" className="dm-document-title" onClick={preview}>{documentTitleParts(row.name).title}</button><span className="dm-version">{row.version}</span></div><p className="dm-row-meta">{submissionDate(row.createdAt)}</p>{!terminal&&problems.length>0&&<p className="dm-row-error">{problems[0]}</p>}</div></div><div className="dm-row-side"><span className={'dm-submission-status '+status.tone}>{status.label}</span><DocumentRowActions row={row} own={own} manage={manage} boss={boss} busy={busy} review={review} start={start} act={act} audit={audit} correct={correct} reupload={reupload} compact details={()=>setDetails(true)}/></div>
 <SubmissionProgress row={row}/>
 {details&&<DocumentModal open title={documentTitleParts(row.name).title} description="资料信息与处理详情" onClose={()=>setDetails(false)}><dl className="grid grid-cols-[90px_1fr] gap-3 text-sm"><dt>归属部门</dt><dd>{row.department}</dd><dt>查看范围</dt><dd>{documentScope(row).label}</dd><dt>当前状态</dt><dd>{status.label}</dd><dt>提交时间</dt><dd>{submissionDate(row.createdAt)}</dd></dl>{row.review_reasons?.length? <p className="text-sm leading-7">送审原因：{row.review_reasons.join('；')}</p>:null}{problems.map(reason=><p className="dm-row-error" key={reason}>{reason}</p>)}<div className="dm-modal-actions"><button type="button" className="dm-primary" onClick={()=>{setDetails(false);audit()}}>查看操作记录</button></div></DocumentModal>}
 </article>
}

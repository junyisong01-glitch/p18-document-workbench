import {canRetryParse} from '../lib/document-workflow'
import {DocumentMore,type DocumentAction} from './BusinessDocumentTools'
import {WorkflowButton,type BusinessRow} from './BusinessPresentation'

export function DocumentRowActions({row,own,manage,boss,busy,review,start,act,audit,correct,reupload}:{row:BusinessRow;own:boolean;manage:boolean;boss:boolean;busy:boolean;review:()=>void;start:(action:string)=>void;act:(action:string)=>void;audit:()=>void;correct:()=>void;reupload:()=>void}){
 const b=row.workflow,current=b.status==='published'&&!b.archived&&!b.deleted,pending=!b.deleted&&!b.archived&&['submitted','approved','correction_pending','returned'].includes(b.status)
 const reviewReason=!boss&&own&&!!row.review_reasons?.length?'本人提交的高风险文档由管理层负责人审核':undefined
 const indexReason=row.index_error?'索引失败，请先重试':!row.technical_index_ready?'等待索引就绪':undefined
 const more:DocumentAction[]=[]
 const add=(label:string,action:string,danger=false)=>more.push({label,run:()=>start(action),danger,disabled:busy})
 if(own||manage)more.push({label:'操作记录',run:audit})
 if(current){
  if(own)more.push({label:'轻量勘误',run:correct})
  if(manage&&(!b.restricted||boss)){add('授权借阅','share');add('撤销借阅','revoke_share')}
  if(boss&&!b.restricted){add(b.company_internal?'撤销公司内部共享':'全公司内部可见',b.company_internal?'revoke_internal':'make_internal');add(b.company_public?'撤销对外公开':'设为对外公开',b.company_public?'revoke_public':'make_public')}
 }
 if(pending&&own&&b.status==='correction_pending')add('取消本次勘误','cancel_correction')
 if(pending&&own&&['submitted','approved','returned'].includes(b.status))add('撤回提交','withdraw')

 if(pending&&manage&&row.publication_stage==='解析异常'&&b.status==='submitted')add('退回并说明原因','return')
 if(!b.deleted&&(manage||own&&b.status==='withdrawn'))add('移入回收站','trash',true)
 if(b.deleted&&(manage||own&&b.status==='withdrawn'))add('恢复记录','restore')
 if(b.deleted&&boss)add('彻底删除','purge',true)
 return <div className="dm-row-actions">
 {pending&&manage&&row.publication_stage==='解析异常'&&row.technical_state==='review'&&<WorkflowButton onClick={review}>核对解析内容</WorkflowButton>}
 {pending&&(manage||own)&&row.technical_state==='failed'&&canRetryParse(row)&&<WorkflowButton busy={busy} onClick={()=>start('retry_parse')}>重试处理</WorkflowButton>}
 {pending&&(manage||own)&&row.technical_state==='failed'&&['submitted','approved'].includes(b.status)&&<WorkflowButton busy={busy} onClick={reupload}>更换文件</WorkflowButton>}
 {!b.deleted&&!b.archived&&['withdrawn','returned'].includes(b.status)&&(own||manage)&&<WorkflowButton busy={busy} onClick={reupload}>重新上传</WorkflowButton>}
 {pending&&manage&&row.publication_stage==='内容待审'&&<><WorkflowButton busy={busy} reason={reviewReason||(row.review_reasons?.length?indexReason:undefined)} onClick={()=>start(row.review_reasons?.length?'approve_publish':'approve')}>{row.review_reasons?.length?'审核并发布':'审核通过'}</WorkflowButton><WorkflowButton busy={busy} onClick={()=>start('return')}>退回修改</WorkflowButton></>}
 {pending&&row.publication_stage==='待发布'&&(manage||own&&b.status==='submitted')&&<WorkflowButton busy={busy} reason={indexReason||reviewReason} onClick={()=>act('publish')}>发布入库</WorkflowButton>}
 {pending&&(manage||own)&&row.index_error&&<WorkflowButton busy={busy} onClick={()=>act('retry_index')}>重试索引</WorkflowButton>}
 <DocumentMore actions={more}/></div>
}

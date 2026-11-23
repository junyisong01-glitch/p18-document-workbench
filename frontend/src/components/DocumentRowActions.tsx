import {canRetryParse} from '../lib/document-workflow'
import {DocumentMore,type DocumentAction} from './BusinessDocumentTools'
import {WorkflowButton,type BusinessRow} from './BusinessPresentation'

export function DocumentRowActions({row,own,manage,boss,busy,review,start,act,audit,correct,reupload,compact=false,details}:{row:BusinessRow;own:boolean;manage:boolean;boss:boolean;busy:boolean;review:()=>void;start:(action:string)=>void;act:(action:string)=>void;audit:()=>void;correct:()=>void;reupload:()=>void;compact?:boolean;details?:()=>void}){
 const b=row.workflow,current=b.status==='published'&&!b.archived&&!b.deleted,pending=!b.deleted&&!b.archived&&['submitted','approved','correction_pending','returned'].includes(b.status)
 const reviewReason=!boss&&own&&!!row.review_reasons?.length?'本人提交的高风险文档由管理层负责人审核':undefined
 const indexReason=row.index_error?'索引失败，请先重试':!row.technical_index_ready?'等待索引就绪':undefined
 const more:DocumentAction[]=[]
 if(details)more.push({label:'资料详情',run:details})
 const add=(label:string,action:string,danger=false)=>more.push({label,run:()=>start(action),danger,disabled:busy})
 if(own||manage)more.push({label:'操作记录',run:audit})
 if(current){
  if(boss)add('紧急下架','take_down',true)
  if(own)more.push({label:'轻量勘误',run:correct})
  if(manage&&(!b.restricted||boss)){add('跨部门授权','share');if(row.active_borrowings?.length)add('撤销借阅','revoke_share')}
  if(boss&&!b.restricted){add(b.company_internal?'撤销公司内部共享':'全公司内部可见',b.company_internal?'revoke_internal':'make_internal');add(b.company_public?'撤销对外公开':'设为对外公开',b.company_public?'revoke_public':'make_public')}
 }
 if(pending&&own&&b.status==='correction_pending')add('取消本次勘误','cancel_correction')
 if(pending&&own&&['submitted','approved','returned'].includes(b.status))add('撤回提交','withdraw')

 if(pending&&manage&&row.publication_stage==='解析异常'&&b.status==='submitted')add('退回并说明原因','return')
 if(!b.deleted&&(manage||own&&b.status==='withdrawn'))add('移入回收站','trash',true)
 if(b.deleted&&(manage||own&&b.status==='withdrawn'))add('恢复记录','restore')
 if(b.deleted&&boss)add('彻底删除','purge',true)
 const primary:Array<{label:string;run:()=>void;reason?:string}>=[]
 if(pending&&manage&&row.publication_stage==='解析异常'&&row.technical_state==='review')primary.push({label:'核对解析内容',run:review})
 if(pending&&(manage||own)&&row.technical_state==='failed'&&canRetryParse(row))primary.push({label:'重试处理',run:()=>start('retry_parse')})
 if(pending&&(manage||own)&&row.technical_state==='failed'&&['submitted','approved'].includes(b.status))primary.push({label:'更换文件',run:reupload})
 if(!b.deleted&&!b.archived&&['withdrawn','returned'].includes(b.status)&&(own||manage))primary.push({label:'重新上传',run:reupload})
 if(pending&&manage&&row.publication_stage==='内容待审'){
  if(!compact)primary.push({label:row.review_reasons?.length?'审核并发布':'审核通过',reason:reviewReason||(row.review_reasons?.length?indexReason:undefined),run:()=>start(row.review_reasons?.length?'approve_publish':'approve')},{label:'退回修改',run:()=>start('return')})
 }
 if(pending&&(manage||own)&&row.index_error)primary.push({label:'重试索引',run:()=>act('retry_index')})
 else if(pending&&row.publication_stage==='自动发布中'&&b.auto_publish_error&&(manage||own))primary.push({label:'重试发布',reason:indexReason,run:()=>act('publish')})
 else if(pending&&row.publication_stage==='待发布'&&(manage||own&&b.status==='submitted')&&(!compact||!indexReason&&!reviewReason))primary.push({label:'发布入库',reason:indexReason||reviewReason,run:()=>act('publish')})
 const visible=compact?primary.slice(0,1):primary
 if(compact)primary.slice(1).forEach(action=>more.push({label:action.label,run:action.run,disabled:busy||!!action.reason}))
 return <div className="dm-row-actions">{visible.map(action=><WorkflowButton key={action.label} busy={busy} reason={action.reason} onClick={action.run}>{action.label}</WorkflowButton>)}<DocumentMore actions={more} compact={compact}/></div>
}

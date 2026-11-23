import type {BusinessRow} from '../components/BusinessPresentation'

export const submissionFilters=['全部','待我处理','处理中','解析异常','待审核','待发布','已退回','已撤回','已发布','已下架','历史归档']
export function submissionState(row:BusinessRow){
 const b=row.workflow
 if(b.deleted)return '回收站'
 if(b.archived)return '历史归档'
 if(b.status==='withdrawn')return '已撤回'
 if(b.status==='returned')return '已退回'
 if(b.status==='published')return '已发布'
 if(b.status==='taken_down')return '已下架'
 if(row.technical_state==='failed'||row.publication_stage==='解析异常')return '解析异常'
 if(row.publication_stage==='内容待审')return '待审核'
 if(row.publication_stage==='待发布'&&row.technical_index_ready)return '待发布'
 return '处理中'
}
export function needsSubmissionAction(row:BusinessRow){
 return ['解析异常','已退回','待发布'].includes(submissionState(row))||(!row.workflow.deleted&&!row.workflow.archived&&!['published','withdrawn','taken_down'].includes(row.workflow.status)&&!!(row.index_error||row.workflow.correction_error||row.workflow.auto_publish_error))
}
export function matchesSubmission(row:BusinessRow,filter:string){
 return filter==='全部'||(filter==='待我处理'?needsSubmissionAction(row):submissionState(row)===filter)
}
// Only offer a retry for a recognisable transient failure; unknown/file errors need inspection or replacement.
export function canRetryParse(row:BusinessRow){
 const message=row.technical_error||''
 return row.technical_state==='failed'&&!/损坏|格式|扩展名|加密|密码|不支持|未安装|缺少|not installed|unsupported|invalid|corrupt/i.test(message)&&/超时|timeout|timed out|暂时不可用|暂不可用|temporarily unavailable|connection reset|连接中断/i.test(message)
}
export function canReviewSubmission(row:BusinessRow,username:string,boss:boolean,head:boolean,department:string){
 return !row.workflow.deleted&&!row.workflow.archived&&row.publication_stage==='内容待审'&&(boss||head&&row.workflow.department===department&&!(row.workflow.owner===username&&!!row.review_reasons?.length))
}

export function submissionGroup(row:BusinessRow,manage:boolean){
 const state=submissionState(row)
 if(['已发布','已撤回','已下架','历史归档','回收站'].includes(state))return '提交记录'
 if(state==='解析异常'&&row.technical_state!=='failed'&&!manage&&!row.index_error&&!row.workflow.correction_error)return '处理中'
 return needsSubmissionAction(row)?'需要处理':'处理中'
}
export function submissionLabel(row:BusinessRow,manage:boolean){
 const state=submissionState(row)
 if(state==='已发布')return {label:row.technical_index_ready?'已发布':'已发布 · 暂不可检索',tone:row.technical_index_ready?'success':'pending'}
 if(['已撤回','已下架','历史归档','回收站'].includes(state))return {label:state,tone:'muted'}
 if(state==='已退回')return {label:'需要修改',tone:'attention'}
 if(row.workflow.auto_publish_error)return {label:'发布需要处理',tone:'attention'}
 if(row.workflow.correction_error)return {label:'勘误需要处理',tone:'attention'}
 if(row.index_error)return {label:'需要重试处理',tone:'attention'}
 if(state==='解析异常')return {label:row.technical_state==='failed'?(canRetryParse(row)?'可重试处理':'需要更换文件'):manage?'需要核对解析':'等待解析核对',tone:submissionGroup(row,manage)==='需要处理'?'attention':'pending'}
 if(state==='待审核')return {label:'等待审核',tone:'pending'}
 if(row.publication_stage==='自动发布中')return {label:row.technical_index_ready?'正在自动发布':'处理中',tone:'pending'}
 if(state==='待发布')return {label:'可以发布',tone:'attention'}
 return {label:row.workflow.correction?'勘误处理中':'处理中',tone:'pending'}
}
export function submissionDate(value:string){
 const date=new Date(value)
 return Number.isFinite(date.getTime())?'提交于 '+new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(date):'提交时间未记录'
}

export type SubmissionStep={label:string;state:'done'|'current'|'waiting'|'error'|'stopped'}
export function submissionProgress(row:BusinessRow):SubmissionStep[]{
 const b=row.workflow,state=submissionState(row)
 const first:SubmissionStep={label:b.correction?'已提交勘误':'已提交',state:'done'}
 // Stopped submissions do not imply that parsing or review ever completed.
 if(['已撤回','已退回','已下架','历史归档','回收站'].includes(state))return [first,{label:state,state:state==='已退回'?'error':'stopped'}]
 const published=b.status==='published'
 const needsReview=!!row.review_reasons?.length||row.publication_stage==='内容待审'||b.status==='approved'||(!b.correction&&!!b.approved_by)
 const labels=[first.label,'解析检查',...(needsReview?['内容审核']:[]),'索引准备',b.correction?'自动生效':'自动发布']
 const index=labels.length-2,last=labels.length-1
 let current=1,error=false
 if(published){current=last;labels[last]=b.correction?'已生效':'已发布'}
 else if(row.publication_stage==='解析异常'||row.technical_state==='failed'){
   labels[1]=row.technical_state==='failed'?'解析失败':'待解析核对';error=true
 }else if(['解析处理中'].includes(row.publication_stage||'')||['queued','converting','parsing'].includes(row.technical_state)){
   labels[1]='正在解析'
 }else if(row.publication_stage==='内容待审'){current=2;labels[2]='等待内容审核'}
 else if(row.technical_state==='ready'||['自动发布中','勘误处理中','待发布'].includes(row.publication_stage||'')||b.status==='approved'){
   current=index
   if(row.technical_index_ready)current=last
   if(row.index_error){current=index;error=true;labels[index]='索引异常'}
   else if(b.auto_publish_error||b.correction_error){current=last;error=true;labels[last]=b.correction?'生效异常':'发布异常'}
   else if(current===last)labels[last]=row.publication_stage==='待发布'?'可以发布':b.correction?'正在自动生效':'正在自动发布'
 }
 const steps:SubmissionStep[]=labels.map((label,i)=>({label,state:i<current?'done':i===current?(error?'error':'current'):'waiting'}))
 // Published is a lifecycle fact; lost/unavailable index must not appear completed.
 if(published&&!row.technical_index_ready)steps[index]={label:'索引未就绪',state:'error'}
 return steps
}

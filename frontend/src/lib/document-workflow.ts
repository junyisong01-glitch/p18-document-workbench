import type {BusinessRow} from '../components/BusinessPresentation'

export const submissionFilters=['全部','待我处理','处理中','解析异常','待审核','待发布','已退回','已撤回','已发布','已下架']
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
 return ['解析异常','已退回','待发布'].includes(submissionState(row))||(!row.workflow.deleted&&!row.workflow.archived&&!['published','withdrawn','taken_down'].includes(row.workflow.status)&&!!(row.index_error||row.workflow.correction_error))
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

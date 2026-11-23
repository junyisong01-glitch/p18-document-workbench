import {Check, Circle, CircleAlert, CircleDot} from 'lucide-react'
import {useId} from 'react'
import type {LibraryRecord} from '@/lib/api'
export const BUSINESS_DEPARTMENTS=['研发部','生产制造部','财务部','人力资源部','行政安全部']
export type Workflow={version:number;owner:string;department:string;status:string;archived:boolean;deleted:boolean;company_public:boolean;company_internal?:boolean;restricted:boolean;legacy:boolean;series:string;read_jobs?:string[];correction?:boolean;correction_error?:string;auto_publish_error?:string;published_by?:string;approved_by?:string|null}
export type BusinessRow=LibraryRecord&{workflow:Workflow;technical_state:string;technical_index_ready:boolean;technical_error?:string;publication_stage?:string;review_reasons?:string[];parse_reasons?:string[];index_error?:string}
export const workflowControl='rounded-md border border-border bg-card px-3 py-2 text-[12px] transition-colors hover:border-[hsl(12_74%_42%/0.5)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] disabled:cursor-not-allowed disabled:opacity-45'
export function WorkflowButton({children,onClick,reason,busy=false,danger=false}:{children:string;onClick:()=>void;reason?:string;busy?:boolean;danger?:boolean}){
 const id=useId()
 return <span className="workflow-action inline-flex" title={reason} tabIndex={reason?0:undefined}><button type="button" className={workflowControl+(danger?' text-[hsl(4_72%_36%)]':'')} disabled={busy||!!reason} aria-describedby={reason?id:undefined} onClick={onClick}>{children}</button>{reason&&<span id={id} className="workflow-disabled-reason sr-only">{reason}</span>}</span>
}
export function workflowState(row:BusinessRow){
 const b=row.workflow
 if(b.deleted)return{label:'回收站',tone:'muted'}
 if(b.status==='taken_down')return{label:'已下架',tone:'muted'}
 if(b.archived)return{label:'历史归档',tone:'muted'}
 if(b.status==='withdrawn')return{label:'已撤回',tone:'muted'}
 if(b.status==='returned')return{label:'已退回',tone:'error'}
 if(b.auto_publish_error)return{label:'发布需要处理',tone:'error'}
 if(row.index_error)return{label:'索引失败',tone:'error'}
 if(row.publication_stage)return{label:row.publication_stage==='待发布'?(row.technical_index_ready?'可以发布':'处理中'):row.publication_stage,
   tone:row.publication_stage==='解析异常'?'error':row.publication_stage==='待发布'&&row.technical_index_ready?'ready':'pending'}
 if(row.technical_state==='failed')return{label:'解析失败',tone:'error'}
 if(b.status==='correction_pending')return{label:b.correction_error?'勘误冲突':'勘误处理中',tone:b.correction_error?'error':'pending'}
 if(b.status==='submitted')return{label:row.technical_state==='review'?'待解析复核':row.technical_state==='ready'?'待业务审核':'解析处理中',tone:'pending'}
 if(b.status==='approved')return{label:row.technical_index_ready?'待发布 · 索引就绪':'审核通过 · 索引准备',tone:row.technical_index_ready?'ready':'pending'}
 if(b.status==='published')return{label:row.technical_index_ready?'已发布 · 可检索':'已发布 · 索引待就绪',tone:row.technical_index_ready?'success':'pending'}
 return{label:'未发布',tone:'muted'}
}
export function WorkflowBadge({row}:{row:BusinessRow}){
 const {label,tone}=workflowState(row)
 const color=tone==='success'?'border-[hsl(148_32%_32%/0.35)] bg-[hsl(148_32%_32%/0.06)] text-[hsl(148_32%_26%)]':tone==='error'?'border-[hsl(4_72%_36%/0.35)] bg-[hsl(4_72%_36%/0.04)] text-[hsl(4_72%_36%)]':tone==='pending'?'border-[hsl(36_68%_38%/0.35)] bg-[hsl(36_68%_38%/0.06)] text-[hsl(36_60%_30%)]':tone==='ready'?'border-sky-700/30 bg-sky-700/5 text-sky-800':'border-border bg-secondary text-muted-foreground'
 return <span className={'workflow-badge inline-flex items-center gap-1.5 rounded-sm border px-2 py-1 text-[11px] font-medium '+color}><span className="size-1.5 shrink-0 rounded-full bg-current"/>{label}</span>
}
export function WorkflowTimeline({row}:{row:BusinessRow}){
 const b=row.workflow
 if(b.status==='withdrawn'&&!b.archived&&!b.deleted)return <p className="dm-terminal-note">已撤回，不会进入检索。需要继续时可重新上传；不再使用可移入回收站。</p>
 if(b.deleted||b.archived||['taken_down','published'].includes(b.status))return null
 if(row.publication_stage)return null
 const labels=b.correction?['已提交勘误','解析与必要复核','索引准备','自动切换生效']:['已提交','解析与技术复核','业务审核','索引准备','待发布','已发布']
 const interrupted=row.technical_state==='failed'||b.status==='returned'||b.deleted||!!b.correction_error||b.status==='withdrawn'
 let stage=b.correction?(b.status==='published'?3:row.technical_state==='ready'?2:1):(b.status==='published'||b.status==='legacy_archived'?5:b.status==='approved'?row.technical_index_ready?4:3:row.technical_state==='ready'?2:1)
 if(b.status==='returned')stage=2
 return <section aria-label="提交进度" className="mt-4 border-t border-dashed border-border pt-4"><ol className="flex flex-wrap gap-y-3">{labels.map((label,i)=>{const done=i<stage,current=i===stage;const Icon=current&&interrupted?CircleAlert:done?Check:current?CircleDot:Circle;return <li key={label} aria-current={current?'step':undefined} className="flex items-center">{i>0&&<span className={'mx-2 h-px w-4 '+(done?'bg-[hsl(148_32%_32%/0.4)]':'bg-border')}/>}<Icon className={'mr-1.5 size-3.5 '+(current&&interrupted?'text-[hsl(4_72%_36%)]':done?'text-[hsl(148_32%_32%)]':'text-muted-foreground')}/><span className={'text-[11px] '+(current?'font-semibold':'text-muted-foreground')}>{label}</span></li>})}</ol><p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{b.correction?'勘误免业务审批，索引有效后自动生效；处理中旧版本继续提供检索。':'进度来自服务端当前状态；具体处理人、时间及退回原因见操作记录。'}{b.archived?' 此版本已归档，仅供有权人员查阅。':''}</p></section>
}
export const businessRoleName=(role?:string)=>({boss:'管理层负责人',supervisor:'部门主管',employee:'员工',guest:'只读访客'}as Record<string,string>)[role||'']||'未分配业务角色'

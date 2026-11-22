import {useEffect,useRef,useState}from 'react'
import {PageHeader}from '@/components/bits'
import {DocPreviewDialog}from '@/components/DocView'
import {HistoryContentSearch}from '@/components/HistoryContentSearch'
import {InviteAccount,MinorCorrection}from '@/components/EnterpriseActions'
import {ReviewDialog}from '@/components/DocAdmin'
import {api}from '@/lib/api'
import {useSession,toDoc}from '@/lib/session'
import type{Doc}from '@/lib/types'
import {useSearchParams}from 'react-router'
import {Plus,Search,SlidersHorizontal}from 'lucide-react'
import {DocumentViews,DocumentFormat,DocumentModal}from '@/components/DocumentLayout'
import {WorkflowBadge,WorkflowTimeline,type BusinessRow as Row}from '@/components/BusinessPresentation'
import {BusinessUpload} from '@/components/BusinessUpload'
import {DocumentRowActions} from '@/components/DocumentRowActions'
import {BorrowerPicker,DocumentAudit,documentScope,scopeOptions} from '@/components/BusinessDocumentTools'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {submissionFilters,matchesSubmission,canReviewSubmission,canRetryParse} from '@/lib/document-workflow'
import { documentTitleParts } from '../lib/document-title'
const depts=['研发部','生产制造部','财务部','人力资源部','行政安全部']
const control='rounded-md border border-border bg-card px-3 py-2 text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] disabled:opacity-40'
export default function BusinessPage(){
 const {user,refresh}=useSession();const [rows,setRows]=useState<Row[]>([]),[tab,setTab]=useState('可查阅资料'),[error,setError]=useState(''),[busy,setBusy]=useState(false),[preview,setPreview]=useState<Doc|null>(null),[review,setReview]=useState<Doc|null>(null)
 const [params]=useSearchParams()
 const [departmentFilter,setDepartmentFilter]=useState('全公司总览'),[query,setQuery]=useState(''),[classificationFilter,setClassificationFilter]=useState(''),[scopeFilter,setScopeFilter]=useState(''),[loaded,setLoaded]=useState(false)
 const [replacement,setReplacement]=useState<Row|undefined>()
 const [people,setPeople]=useState<Array<{username:string;role:string;department:string}>>([]),[person,setPerson]=useState(''),[personRole,setPersonRole]=useState('employee'),[personDept,setPersonDept]=useState('研发部')
 const [correcting,setCorrecting]=useState<string|null>(null),[submitOpen,setSubmitOpen]=useState(false),[feedback,setFeedback]=useState('')
 const [moreFilters,setMoreFilters]=useState(false),[submissionFilter,setSubmissionFilter]=useState('全部')
 const [auditRow,setAuditRow]=useState<Row|null>(null)
 const [target,setTarget]=useState<Row|null>(null),[operation,setOperation]=useState(''),[note,setNote]=useState(''),[recipient,setRecipient]=useState(''),[confirmation,setConfirmation]=useState('')
 const boss=user?.accessRole==='boss',head=user?.accessRole==='supervisor',guest=user?.accessRole==='guest'
 const canFilterAccess=!!(boss||head),accessFilterCount=Number(!!classificationFilter)+Number(!!scopeFilter)
 const lastRows=useRef(''),requestSeq=useRef(0),mounted=useRef(true)
 async function load(){const request=++requestSeq.current;try{const next=await api.get<Row[]>('/api/business/documents');if(!mounted.current||request!==requestSeq.current)return;setRows(next);setLoaded(true);const signature=JSON.stringify(next.map(r=>[r.id,r.workflow.version,r.workflow.status,r.technical_state,r.technical_index_ready]));if(lastRows.current&&signature!==lastRows.current)void refresh();lastRows.current=signature}catch(e){if(mounted.current)setError((e as Error).message)}}
 useEffect(()=>{mounted.current=true;void load();const t=setInterval(()=>{void load()},3500);return()=>{mounted.current=false;requestSeq.current++;clearInterval(t)}},[])
 useEffect(()=>{if(params.get('search'))setQuery(params.get('search')!);const selected=params.get('view');if(selected==='提交资料'||selected==='上传资料'){setSubmitOpen(!guest);setTab('我的提交')}else if(selected){if(['解析异常','待发布','已退回','已撤回'].includes(selected)&&!(boss||head)){setTab('我的提交');setSubmissionFilter(selected)}else{setTab(({已发布:'可查阅资料',内容待审:'待我审核',待审核:'待我审核',解析异常:'部门异常'} as Record<string,string>)[selected]||selected);setSubmissionFilter('全部')}}},[params,boss,head,guest])
 useEffect(()=>{if(boss)api.get<typeof people>('/api/business/people').then(setPeople).catch(()=>{})},[boss])
 function doc(row:Row):Doc{return {...toDoc(row),kbId:'business'}}
 function start(row:Row,action:string){setTarget(row);setOperation(action);setNote('');setRecipient('');setConfirmation('');setError('')}
 async function actOn(row:Row,action:string){
   if(busy)return
   setBusy(true);setError('')
   try{await api.post('/api/business/documents/'+row.id+'/action',{action,expected:row.workflow.version});setFeedback(action==='publish'?'资料已发布。':'已请求重试索引。');await load();await refresh()}
   catch(e){setError((e as Error).message)}
   finally{setBusy(false)}
 }
 async function act(){if(!target||busy)return;setBusy(true);setError('');try{await api.post('/api/business/documents/'+target.id+'/action',{action:operation,expected:target.workflow.version,note,username:recipient,confirm:confirmation});setTarget(null);setFeedback('操作已完成，状态以服务端最新记录为准。');await load();await refresh()}catch(e){setError((e as Error).message)}finally{setBusy(false)}}

 const tabs=['可查阅资料',...(!guest?['我的提交']:[]),...((boss||head)?['待我审核','部门异常','待发布']:[]),'历史归档',...(!guest?['回收站']:[]),...(boss?['人员职责']:[]),...(user?.canCreateAccounts?['邀请建号']:[])]
 const activeTab=tabs.includes(tab)?tab:'可查阅资料'
 function ownRow(row:Row){return row.workflow.owner===user?.username&&(boss||row.department===user?.role.dept)}
 function inView(row:Row,view:string){
  const b=row.workflow
  if(view==='回收站')return b.deleted
  if(b.deleted)return false
  if(view==='历史归档')return b.archived
  if(b.archived)return false
  if(view==='我的提交')return b.owner===user?.username
  if(view==='待我审核')return canReviewSubmission(row,user?.username||'',!!boss,!!head,user?.role.dept||'')
  if(['部门异常','待发布'].includes(view))return row.publication_stage===(view==='部门异常'?'解析异常':view)&&(boss||head&&b.department===user?.role.dept)
  return b.status==='published'
 }
 const scopedRows=rows.filter(row=>!boss||departmentFilter==='全公司总览'||row.department===departmentFilter)
 const viewCounts=Object.fromEntries(tabs.filter(view=>!['人员职责','邀请建号'].includes(view)).map(view=>[view,scopedRows.filter(row=>inView(row,view)).length]))
 const myRows=scopedRows.filter(row=>inView(row,'我的提交'))
 const submissionCounts=Object.fromEntries(submissionFilters.map(filter=>[filter,myRows.filter(row=>matchesSubmission(row,filter)).length]))
 const queryText=query.trim().toLowerCase()
 const list=scopedRows.filter(row=>inView(row,activeTab)&&(activeTab!=='我的提交'||matchesSubmission(row,submissionFilter))).filter(row=>(!canFilterAccess||!scopeFilter||documentScope(row).key===scopeFilter)&&(!canFilterAccess||!classificationFilter||row.classification===classificationFilter)&&(!queryText||[row.name,documentTitleParts(row.name).title,row.code,row.id].some(value=>value.toLowerCase().includes(queryText))))
 function openSubmit(){setReplacement(undefined);setError('');setSubmitOpen(true)}

 const groups=boss&&departmentFilter==='全公司总览'?Array.from(new Set([...depts,...list.map(r=>r.department)])).map(d=>({department:d,rows:list.filter(r=>r.department===d)})).filter(g=>g.rows.length):[{department:boss?departmentFilter:activeTab==='可查阅资料'?'可查阅资料':activeTab,rows:list}]
 const opLabels:Record<string,string>={withdraw:'撤回提交',take_down:'下架',retry_index:'重试索引',approve_publish:'审核并发布',cancel_correction:'取消未生效勘误',retry_parse:'重试解析',approve:'审核通过并准备索引',return:'退回修改',resubmit:'重新提交',publish:'发布入库',archive:'归档',trash:'移入回收站',restore:'恢复（保留原归档状态）',share:'授权借阅',revoke_share:'撤销借阅',make_public:'设为对外公开',revoke_public:'撤销对外公开',make_internal:'设为全公司内部可见',revoke_internal:'撤销全公司内部可见',purge:'彻底删除'}
 return <div className="document-manager space-y-5"><PageHeader kicker="Documents" title="文档管理" desc="查阅你有权查看的资料，或跟进自己上传的文件。普通资料检查通过后即可发布。" extra={!guest?<button type="button" className="dm-primary" aria-label="上传资料" disabled={busy} onClick={openSubmit}><Plus size={16}/>上传资料</button>:undefined}/><p className="text-[12px] text-muted-foreground">当前账号：{user?.username} · {user?.role.dept} · {({boss:'管理层负责人',supervisor:'部门主管',employee:'员工',guest:'只读访客'}as Record<string,string>)[user?.accessRole||'']||'未分配业务角色'}</p>
 <div className="dm-navigation"><DocumentViews tabs={tabs} active={activeTab} counts={viewCounts} loaded={loaded} onSelect={value=>{setTab(value);setQuery('')}}/></div>
 {error&&<p role="alert" className="border-l-2 border-[hsl(12_74%_42%)] pl-3 text-[13px]">{error}</p>}
 {activeTab==='邀请建号'?<InviteAccount/>:activeTab==='人员职责'?<section className="space-y-4 rounded-lg border border-border bg-card p-6"><h2>管理层负责人：任免部门主管</h2><p className="text-xs text-muted-foreground">保存会使该账号旧会话失效；不能在此增加第二个管理层负责人。岗位例外与文档授权仍独立生效。</p><label>账号<select aria-label="账号" className={control} value={person} onChange={e=>setPerson(e.target.value)}><option value="">选择账号</option>{people.filter(p=>p.role!=='boss').map(p=><option key={p.username}>{p.username}</option>)}</select></label><label>职责<select aria-label="职责" className={control} value={personRole} onChange={e=>setPersonRole(e.target.value)}><option value="employee">员工</option><option value="supervisor">部门主管</option><option value="guest">只读访客</option></select></label><label>部门<select aria-label="部门" className={control} value={personDept} onChange={e=>setPersonDept(e.target.value)}>{depts.map(d=><option key={d}>{d}</option>)}</select></label><button className={control} disabled={!person||busy} onClick={async()=>{setBusy(true);try{await api.put('/api/business/people',{username:person,role:personRole,department:personDept});setPeople(await api.get<typeof people>('/api/business/people'));setError('职责已更新，目标账号须重新登录')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>确认调整职责</button><ul className="space-y-2 text-sm">{people.map(p=><li key={p.username}>{p.username} · {p.department||'无部门读权'} · {p.role}</li>)}</ul></section>:<section className="space-y-5">
 {(boss||head)&&<p className="border-l-2 border-[hsl(12_74%_42%/0.5)] pl-3 text-xs leading-relaxed text-muted-foreground">{boss?'全公司资料按部门分类。可处理本人及其他人的提交，管理操作记录在文档审计中。':'管理本部门提交。本人提交的高风险资料交由管理层负责人审核。'}</p>}
 {boss&&<nav aria-label="部门分类" className="flex flex-wrap gap-1.5 rounded-lg border border-border bg-card p-2">{['全公司总览',...depts].map(d=><button type="button" key={d} aria-pressed={departmentFilter===d} className={control+(departmentFilter===d?' !bg-[hsl(12_74%_42%)] text-white':' border-transparent')} onClick={()=>setDepartmentFilter(d)}>{d}</button>)}</nav>}
 {activeTab==='我的提交'&&<div className="dm-submission-panel"><div className="dm-submission-heading"><strong>我的提交</strong><span>{loaded?(submissionCounts['待我处理']?`${submissionCounts['待我处理']} 份需要你处理`:'当前没有需要你处理的提交'):'正在读取提交状态…'}</span></div><nav aria-label="提交状态" className="dm-submission-filters">{submissionFilters.map(filter=><button type="button" key={filter} aria-pressed={submissionFilter===filter} className={(submissionFilter===filter?'active ':'')+(filter==='待我处理'&&submissionCounts[filter]>0?'attention':'')} onClick={()=>setSubmissionFilter(filter)}>{filter}<span>{loaded?submissionCounts[filter]:'…'}</span></button>)}</nav></div>}
 <div className="flex flex-wrap items-end gap-3"><label className="relative min-w-[220px] flex-1 text-xs"><span className="sr-only">筛选资料</span><Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground"/><input aria-label="筛选资料" placeholder="按名称、编号或文件ID查找" className={control+' w-full pl-9'} value={query} onChange={e=>setQuery(e.target.value)}/></label>{canFilterAccess&&<button type="button" aria-expanded={moreFilters} aria-controls="document-extra-filters" className={control+' flex items-center gap-2'} onClick={()=>setMoreFilters(value=>!value)}><SlidersHorizontal size={15}/>更多筛选{accessFilterCount>0&&<span className="rounded bg-secondary px-1.5 text-xs">{accessFilterCount}</span>}</button>}<span role="status" className="pb-2 text-xs text-muted-foreground">{loaded?`${list.length} 份资料`:'正在加载真实资料…'}</span></div>
 {canFilterAccess&&moreFilters&&<div id="document-extra-filters" className="flex flex-wrap items-end gap-3 rounded-lg border border-border bg-card p-4"><label className="grid gap-1 text-xs text-muted-foreground">查看范围<select aria-label="筛选查看范围" className={control} value={scopeFilter} onChange={e=>setScopeFilter(e.target.value)}>{scopeOptions.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label><label className="grid gap-1 text-xs text-muted-foreground">密级<select aria-label="筛选密级" className={control} value={classificationFilter} onChange={e=>setClassificationFilter(e.target.value)}><option value="">全部密级</option>{['公开','内部','机密'].map(value=><option value={value} key={value}>{value}</option>)}</select></label><p className="pb-2 text-xs text-muted-foreground">按内容敏感程度筛选，查看权限仍以资料授权为准。</p></div>}
 {canFilterAccess&&classificationFilter&&<div className="flex items-center gap-2 text-xs text-muted-foreground"><span>已筛选：密级 · {classificationFilter}</span><button type="button" className="underline underline-offset-4" onClick={()=>setClassificationFilter('')}>清除密级筛选</button></div>}
 {canFilterAccess&&scopeFilter&&<div className="flex items-center gap-2 text-xs text-muted-foreground"><span>已筛选：查看范围 · {scopeOptions.find(([value])=>value===scopeFilter)?.[1]}</span><button type="button" className="underline underline-offset-4" onClick={()=>setScopeFilter('')}>清除查看范围筛选</button></div>}
 {activeTab==='历史归档'&&<HistoryContentSearch key={user?.username}/>}
 {!loaded?<div className="animate-pulse space-y-3" aria-label="正在加载资料">{[0,1,2].map(i=><div key={i} className="h-24 rounded-lg bg-secondary/60"/>)}</div>:!list.length?<p className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted-foreground">此视图暂无符合筛选的获准资料。可调整筛选条件；不会显示其他账号的私有提交。</p>:groups.map(group=><section key={group.department} aria-label={group.department+'资料'} className="space-y-3"><h2 className="flex items-center gap-3 text-sm font-semibold">{group.department}<span className="font-mono2 text-xs font-normal text-muted-foreground">{group.rows.length} 份</span></h2><div className="dm-document-list">{group.rows.map(row=>{const b=row.workflow,manage=boss||(head&&b.department===user?.role.dept),own=ownRow(row)
 return <article key={row.id} data-document-id={row.id} data-workflow-version={b.version} className="dm-document-row"><div className="dm-row-main"><DocumentFormat format={row.format} secret={b.restricted} legacy={b.legacy}/><div className="dm-row-copy"><div className="dm-title-line"><button type="button" onClick={()=>setPreview(doc(row))} className="dm-document-title" title={row.name}>{documentTitleParts(row.name).title}</button><span className="dm-version">{row.version}</span>{b.status==='correction_pending'&&<span className="dm-correction">勘误处理中 · 旧内容继续生效</span>}</div><p className="dm-row-meta"><span>{row.department}</span><span title={documentScope(row).description} className={b.restricted?'dm-tag dm-tag-secret':'dm-tag'}>{documentScope(row).label}</span>{b.legacy&&<span className="dm-tag dm-tag-legacy">历史导入资料</span>}</p>{row.review_reasons?.map(reason=><p key={reason} className="dm-row-error">送审原因 · {reason}</p>)}
 {row.parse_reasons?.map(reason=><p key={reason} className="dm-row-error">{reason}</p>)}
 {(row.technical_error||b.correction_error||row.index_error)&&<p role="status" className="dm-row-error">{b.correction_error||row.technical_error||row.index_error}</p>}</div></div><div className="dm-row-side"><div className="dm-state"><WorkflowBadge row={row}/><span title="技术处理状态，独立于业务发布状态">{b.status==='withdrawn'?'已停止流转 · 不参与检索':b.deleted?'已移入回收站':b.archived?'历史记录 · 不参与当前问答':b.status==='taken_down'?'已停止提供检索':(row.technical_state==='ready'?'处理完成':row.technical_state==='review'?'待核对解析':row.technical_state==='failed'?(canRetryParse(row)?'可重试处理':'需要检查文件'):'处理中')+' · '+(row.technical_index_ready?'索引有效':'尚不可检索')}</span></div>{!((activeTab==='我的提交'||activeTab==='部门异常')&&b.owner===user?.username)&&<span className="dm-owner" title={'提交者：'+b.owner}><i>{b.owner==='legacy_import'?'导':(demoIdentityName(b.owner)||(b.legacy?'历史导入':'未登记姓名')).charAt(0)}</i><span>{b.owner==='legacy_import'?'历史导入':demoIdentityName(b.owner)||(b.legacy?'历史导入':'未登记姓名')}</span></span>}<DocumentRowActions row={row} own={own} manage={manage} boss={!!boss} busy={busy} review={()=>setReview(doc(row))} start={action=>start(row,action)} act={action=>{void actOn(row,action)}} audit={()=>setAuditRow(row)} correct={()=>setCorrecting(row.id)} reupload={()=>{setReplacement(row);setError('');setSubmitOpen(true)}}/></div>{activeTab==='我的提交'&&own&&b.status!=='published'&&<WorkflowTimeline row={row}/>}</article>})}</div></section>)}
 </section>}

 {submitOpen&&!guest&&<BusinessUpload replacement={replacement} rows={rows} onClose={()=>{setSubmitOpen(false);setTab('我的提交')}} onUploaded={async()=>{setTab('我的提交');setSubmissionFilter('全部');setQuery('');await load();await refresh()}}/>}
 {feedback&&<div className="dm-feedback" role="status"><span>{feedback}</span><button type="button" aria-label="关闭操作提示" onClick={()=>setFeedback('')}>×</button></div>}

 {target&&<DocumentModal open title={opLabels[operation]+'：'+target.name} label="业务操作确认" busy={busy} onClose={()=>setTarget(null)} description="请核对操作对象与原因。服务器将在执行时再次校验权限和版本。"><div className="dm-operation-form">{error&&<p role="alert" className="dm-form-error">{error}</p>}{operation==='make_public'&&<p className="rounded-md border border-primary/30 bg-primary/5 p-3 text-sm">此操作将允许外部访客检索、阅读和下载这份资料。请确认它可以对外公开。</p>}<p className="dm-operation-note">{operation==='purge'?'彻底删除后无法恢复。':operation==='make_internal'?'允许全公司内部成员查看，不包含访客。':operation==='withdraw'?'停止本次提交流转；已有生效版本不受影响。':operation==='trash'?'移入回收站后不参与检索，可在回收站恢复记录。':'操作会保留处理人和时间，按当前权限生效。'}</p>{['return','take_down'].includes(operation)&&<label className="grid gap-1 text-sm">{operation==='take_down'?'下架原因':'退回原因'}<textarea required className={control} value={note} onChange={e=>setNote(e.target.value)}/></label>}{['share','revoke_share'].includes(operation)&&<BorrowerPicker id={target.id} revoke={operation==='revoke_share'} value={recipient} onChange={setRecipient}/>} {operation==='purge'&&<label className="grid gap-1 text-sm">输入文件ID确认：{target.id}<input className={control} value={confirmation} onChange={e=>setConfirmation(e.target.value)}/></label>}<div className="dm-modal-actions"><button className="dm-primary" disabled={busy||(['share','revoke_share'].includes(operation)&&!recipient)||(operation==='purge'&&confirmation!==target.id)||(['return','take_down'].includes(operation)&&!note.trim())} onClick={act}>确认执行</button><button className={control} disabled={busy} onClick={()=>setTarget(null)}>取消</button></div></div></DocumentModal>}
 {auditRow&&<DocumentAudit row={auditRow} onClose={()=>setAuditRow(null)}/>}
 {correcting&&<MinorCorrection id={correcting} document={rows.find(row=>row.id===correcting)} onClose={()=>setCorrecting(null)} onDone={()=>{setCorrecting(null);void load();void refresh()}}/>}
 <DocPreviewDialog doc={preview} open={!!preview} onClose={()=>setPreview(null)}/><ReviewDialog doc={review} onClose={()=>{setReview(null);void load()}}/>
 </div>
}

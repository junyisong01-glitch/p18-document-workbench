import {useEffect,useRef,useState} from 'react'
import {CloudUpload,FileText,X,CheckCircle2,AlertCircle} from 'lucide-react'
import {useSession} from '@/lib/session'
import {api} from '@/lib/api'
import {documentTitleParts} from '@/lib/document-title'
import {DocumentModal} from './DocumentLayout'
import {BUSINESS_DEPARTMENTS,type BusinessRow} from './BusinessPresentation'

type Match={id:string;name:string;code:string;version:string;department:string;classification:string;expected:number;status:string;failed:boolean;can_replace:boolean;reason:string}
type Item={matches?:Match[];matchKey?:string;matchState?:'loading'|'ready'|'error';choice?:string;key:string;file:File;name:string;code:string;version:string;secret:boolean;status:'selected'|'uploading'|'accepted'|'failed';error:string;id?:string}
const input='rounded-md border border-border bg-card px-3 py-2 text-sm w-full'
function nextVersion(value:string){const match=/^(V?)(\d+)(?:\.(\d+))?$/i.exec(value);return match?`${match[1]}${match[2]}.${Number(match[3]||0)+1}`:''}
export function BusinessUpload({replacement,onClose,onUploaded,rows}:{replacement?:BusinessRow;onClose:()=>void;onUploaded:()=>Promise<void>;rows:BusinessRow[]}){
 const {user}=useSession(),boss=user?.accessRole==='boss'
 const [items,setItems]=useState<Item[]>([]),[department,setDepartment]=useState(replacement?.department|| (boss?'':user?.role.dept||''))
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[drag,setDrag]=useState(false),[matchRetry,setMatchRetry]=useState(0)
 const fileInput=useRef<HTMLInputElement>(null)
 const change=(key:string,patch:Partial<Item>)=>setItems(all=>all.map(item=>item.key===key?{...item,...patch}:item))
 const matchKey=(item:Item)=>JSON.stringify([department,item.name.trim(),item.code.trim()])
 const signature=JSON.stringify(items.filter(i=>i.status==='selected'||i.status==='failed').map(i=>[i.key,matchKey(i)]))
 useEffect(()=>{
  if(busy||!department)return
  let active=true
  const timer=setTimeout(()=>{for(const item of items){
   if(!['selected','failed'].includes(item.status)||!item.name.trim()||item.matchKey===matchKey(item)&&item.matchState==='ready')continue
   const key=matchKey(item);change(item.key,{matchKey:key,matchState:'loading',choice:undefined,error:''})
   api.post<Match[]>('/api/business/upload-match',{name:item.name.trim(),code:item.code.trim(),department}).then(matches=>{
    if(!active)return
    if(replacement)matches=matches.filter(m=>m.id===replacement.id)
    const forced=replacement&&matches.find(m=>m.id===replacement.id&&m.can_replace)
    change(item.key,{matches,matchKey:key,matchState:'ready',choice:forced?forced.id:replacement||matches.length?'':'new',...(forced?{version:forced.status==='withdrawn'||forced.failed?forced.version:nextVersion(forced.version)}:{})})
   }).catch(e=>{if(active)change(item.key,{matchState:'error',error:(e as Error).message})})
  }},250)
  return()=>{active=false;clearTimeout(timer)}
 },[signature,busy,matchRetry])
 function chooseMatch(item:Item,id:string){const match=item.matches?.find(m=>m.id===id);change(item.key,{choice:id,...(match?{version:match.status==='withdrawn'||match.failed?match.version:nextVersion(match.version),secret:item.secret||match.classification==='机密'}:{})})}

 function choose(files:File[]){
  if(busy)return
  const limit=replacement?1:10
  if(items.length+files.length>limit){setError(`一次最多选择 ${limit} 份；请分批上传。`);return}
  if(items.reduce((n,i)=>n+i.file.size,0)+files.reduce((n,f)=>n+f.size,0)>100_000_000){setError('这一批超过 100 MB，请分批上传。');return}
  const accepted:Item[]=[],errors:string[]=[]
  for(const file of files){
   if(!/\.(docx?|xlsx?|pdf|txt|md|csv|jpe?g|png)$/i.test(file.name)){errors.push(`${file.name}：暂不支持此格式。`);continue}
   if(!file.size||file.size>20_000_000){errors.push(`${file.name}：文件为空或超过 20 MB，请拆分后重试。`);continue}
   if([...items,...accepted].some(i=>i.file.name===file.name&&i.file.size===file.size&&i.file.lastModified===file.lastModified)){errors.push(`${file.name}：已在本批列表中。`);continue}
   accepted.push({key:crypto.randomUUID(),file,name:replacement?.name||documentTitleParts(file.name).title,code:replacement?.code||'',version:replacement?(replacement.workflow.status==='withdrawn'?replacement.version:nextVersion(replacement.version)):'V1.0',secret:replacement?.classification==='机密',status:'selected',error:''})
  }
  setItems(current=>[...current,...accepted]);setError(errors.join('\n'))
  if(fileInput.current)fileInput.current.value=''
 }
 async function send(selected:Item[]){
  if(busy||!department||!selected.length)return
  if(selected.some(i=>i.matchState!=='ready'||i.matchKey!==matchKey(i)||!i.choice)){setError('请先确认每份文件是新增资料，还是更新已有资料。');return}
  const replacements=selected.filter(i=>i.choice!=='new').map(i=>i.choice);if(new Set(replacements).size!==replacements.length){setError('同一批不能用多份文件更新同一份资料，请保留一份。');return}
  if(selected.some(i=>!i.name.trim()||!i.version.trim())){setError('请补全文件名称和版本。');return}
  setBusy(true);setError('')
  for(const item of selected){
   change(item.key,{status:'uploading',error:''})
   try{
    const match=item.matches?.find(m=>m.id===item.choice);
    const form=new FormData();form.append('file',item.file);form.append('metadata_json',JSON.stringify({name:item.name.trim(),code:match?match.code:item.code.trim(),version:item.version.trim(),department,classification:item.secret||match?.classification==='机密'?'机密':'内部',...(match?{replaces:match.id,replaces_expected:match.expected}:{})}))
    const response=await fetch('/api/business/upload',{method:'POST',credentials:'same-origin',headers:{'X-P18-Client':'workbench'},body:form})
    const result=await response.json()
    if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'上传失败，请重试。')
    change(item.key,{status:'accepted',id:result.id})
   }catch(e){change(item.key,{status:'failed',error:(e as Error).message})}
  }
  try{await onUploaded()}catch{setError('文件已提交；状态刷新失败，请稍后到“我的提交”查看。')}
  setBusy(false)
 }
 const pending=items.filter(i=>i.status==='selected'||i.status==='failed')
 return <DocumentModal open title={replacement?'重新上传资料':'上传资料'} label={replacement?'重新上传资料':'上传资料'} busy={busy} onClose={onClose} description="最多 10 份，每份不超过 20 MB。选好文件后，会检查是否有可更新的已有资料，由你确认。">
 <div className="space-y-4">
  {boss&&!replacement&&<details className="text-xs text-muted-foreground" open={!department}><summary className="cursor-pointer">代部门上传设置</summary><label className="mt-3 grid gap-2">资料所属部门<select aria-label="所属部门" className={input} disabled={busy} value={department} onChange={e=>setDepartment(e.target.value)}><option value="">请选择资料所属部门</option>{BUSINESS_DEPARTMENTS.map(d=><option key={d}>{d}</option>)}</select></label></details>}
  <label className={'dm-upload-area '+(drag?'dragging':'')} onDragOver={e=>{e.preventDefault();if(!busy)setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);choose(Array.from(e.dataTransfer.files))}}>
   <input ref={fileInput} className="sr-only" aria-label="业务文件" type="file" multiple={!replacement} disabled={busy} accept=".doc,.docx,.pdf,.xlsx,.xls,.txt,.md,.csv,.jpg,.jpeg,.png" onChange={e=>choose(Array.from(e.target.files||[]))}/><CloudUpload size={25}/><strong>拖入文件，或点击选择</strong><span>Word、PDF、Excel、TXT、Markdown、CSV、JPG、PNG</span>
  </label>
  {error&&<p role="alert" className="whitespace-pre-wrap text-sm text-red-700">{error}</p>}
  <div className="space-y-3" aria-label="待上传文件">{items.map((item,index)=>{
   const locked=busy||item.status==='accepted',row=rows.find(r=>r.id===item.id),match=item.matches?.find(m=>m.id===item.choice)
   const stage=row?.index_error?'索引失败':row?.publication_stage==='待发布'?(row.technical_index_ready?'检查完成 · 待你发布':'正在建立索引'):row?.publication_stage||'正在读取内容'
   const attention=!!row?.index_error||row?.publication_stage==='解析异常'||row?.publication_stage==='内容待审'
   return <section key={item.key} className="rounded-lg border border-border bg-card p-4 space-y-3" aria-label={'文件 '+(index+1)}>
    <div className="flex items-start gap-3"><FileText size={18} className="mt-1 shrink-0 text-muted-foreground"/><div className="min-w-0 flex-1"><p className="break-all text-xs text-muted-foreground">{item.file.name} · {(item.file.size/1024).toFixed(1)} KB</p><label className="mt-2 grid gap-1 text-xs">名称<input aria-label={'文件名称 '+(index+1)} className={input} value={item.name} disabled={locked||!!replacement} maxLength={200} onChange={e=>change(item.key,{name:e.target.value})}/></label></div>{!locked&&<button type="button" aria-label={'移除 '+item.file.name} onClick={()=>setItems(all=>all.filter(i=>i.key!==item.key))}><X size={16}/></button>}</div>
    {item.status!=='accepted'&&<div className="dm-upload-match">
     {!department?<p>选择归属部门后检查已有资料。</p>:item.matchState==='error'?<><p role="alert">匹配检查失败：{item.error}</p><button type="button" onClick={()=>{change(item.key,{matchKey:undefined});setMatchRetry(n=>n+1)}}>重新检查</button></>:item.matchState!=='ready'||item.matchKey!==matchKey(item)?<p role="status">正在检查已有资料…</p>:item.matches?.length?<>
      <strong>找到 {item.matches.length} 份可能对应的资料</strong><p>按名称或编号提示，不会自动覆盖。请选择本次上传的用途。</p>
      {item.matches.map(m=><label key={m.id} className="dm-match-option"><input type="radio" name={'match-'+item.key} checked={item.choice===m.id} disabled={locked||!m.can_replace} onChange={()=>chooseMatch(item,m.id)}/><span><b>{m.name} · {m.version}</b><small>{m.reason} · {m.can_replace?(m.status==='withdrawn'?'接续已撤回的提交':m.failed?'修正解析失败的文件':'更新此资料'):'已有处理中提交，请先处理或撤回'}</small></span></label>)}
      {!replacement&&<label className="dm-match-option"><input type="radio" name={'match-'+item.key} checked={item.choice==='new'} disabled={locked} onChange={()=>chooseMatch(item,'new')}/><span>作为独立的新资料<small>保留已有资料，不关联版本；已有编号不能重复使用。</small></span></label>}
      {match&&<><label className="mt-2 grid gap-1">本次版本<input aria-label={'本次版本 '+(index+1)} className={input} value={item.version} disabled={locked} onChange={e=>change(item.key,{version:e.target.value})}/></label><p>检查与发布完成后才替换现行版，原文件保留在历史记录中。新版的共享范围需按权限确认。</p></>}
     </>:<p>{replacement?'原提交状态或权限已变化，请关闭后刷新列表重新操作。':'未发现你有权更新的同名或同编号资料，将作为新资料上传。'}</p>}
    </div>}
    <div className="space-y-1.5 text-xs">
     <label className="flex items-center gap-2"><input type="checkbox" aria-describedby={'restriction-hint-'+item.key} checked={item.secret} disabled={locked||match?.classification==='机密'} onChange={e=>change(item.key,{secret:e.target.checked})}/>这份资料可能需要限制查看</label>
     <p id={'restriction-hint-'+item.key} className="pl-6 text-[11px] leading-6 text-muted-foreground">{match?.classification==='机密'?'原资料已标为机密，新版本保留限制并送审。':'例如未公开方案、客户资料、实验数据；不确定时也可选择，按受限资料交审核人确认。'}未勾选的资料仍会自动检查敏感信息。</p>
    </div>
    <details className="text-xs text-muted-foreground"><summary className="cursor-pointer">更多选项 · 编号与版本</summary><div className="mt-3 grid grid-cols-2 gap-3"><label>文档编号（选填）<input className={input+' mt-1'} value={match?.code||item.code} disabled={locked||!!match||!!replacement} maxLength={200} onChange={e=>change(item.key,{code:e.target.value})}/></label><label>版本<input className={input+' mt-1'} value={item.version} disabled={locked} maxLength={200} onChange={e=>change(item.key,{version:e.target.value})}/></label></div></details>
    {item.status==='uploading'&&<p role="status" className="text-xs text-muted-foreground">正在上传…</p>}
    {item.status==='accepted'&&<p role="status" className={'flex items-center gap-2 text-xs '+(attention?'text-amber-800':'text-emerald-800')}>{attention?<AlertCircle size={14}/>:<CheckCircle2 size={14}/>}已上传 · {stage}</p>}
    {item.status==='failed'&&<div role="alert" className="text-xs text-red-700"><p className="flex gap-2"><AlertCircle size={14} className="shrink-0"/>{item.error}</p><button type="button" className="mt-2 underline" disabled={busy} onClick={()=>void send([item])}>重试这份上传</button></div>}
   </section>
  })}</div>
  {!!items.length&&<p className="text-xs leading-relaxed text-muted-foreground">文件逐份处理，一份失败不影响其他文件。提交完成后可离开此页，在“我的提交”查看解析结果和发布。同名文件不会自动覆盖旧资料。</p>}
  <div className="dm-modal-actions"><button type="button" className="rounded-md border px-4 py-2 text-sm" disabled={busy} onClick={onClose}>{items.some(i=>i.status==='accepted')?'完成，查看我的提交':'取消'}</button>{pending.length>0&&<button type="button" disabled={busy||!department||pending.some(i=>i.matchState!=='ready'||i.matchKey!==matchKey(i)||!i.choice)} className="dm-primary" onClick={()=>void send(pending)}>{busy?'正在上传…':`上传并检查 ${pending.length} 份`}</button>}</div>
 </div></DocumentModal>
}

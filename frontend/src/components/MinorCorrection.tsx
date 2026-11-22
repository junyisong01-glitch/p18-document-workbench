import {useEffect,useRef,useState,type FormEvent} from 'react'
import {Check,CloudUpload,FileText,X} from 'lucide-react'
import {api} from '@/lib/api'
import {documentTitleParts} from '@/lib/document-title'
import {DocumentModal} from './DocumentLayout'
import './MinorCorrection.css'

type Editing={expected:number;format:string;notice:string;paragraphs:Array<{ordinal:number;text:string;editable:boolean}>}
type Props={id:string;document?:{name:string;version:string};onClose:()=>void;onDone:()=>void}
export function MinorCorrection({id,document,onClose,onDone}:Props){
 const [data,setData]=useState<Editing|null>(null),[texts,setTexts]=useState<Record<number,string>>({}),[file,setFile]=useState<File|null>(null)
 const [mode,setMode]=useState<'file'|'text'>('file'),[reason,setReason]=useState(''),[declaration,setDeclaration]=useState(false)
 const [error,setError]=useState(''),[loadError,setLoadError]=useState(''),[fileError,setFileError]=useState(''),[busy,setBusy]=useState(false),[drag,setDrag]=useState(false),[attempt,setAttempt]=useState(0)
 const fileInput=useRef<HTMLInputElement>(null)
 useEffect(()=>{let active=true;setLoadError('');api.get<Editing>('/api/business/documents/'+id+'/editable').then(d=>{if(active)setData(d)}).catch(e=>{if(active)setLoadError(e.message)});return()=>{active=false}},[id,attempt])
 const changes=data?.paragraphs.filter(p=>p.editable&&p.ordinal in texts&&texts[p.ordinal]!==p.text)||[]
 const canSubmit=!!data&&!!reason.trim()&&declaration&&(mode==='file'?!!file:changes.length>0)&&!busy
 const format=data?.format.slice(1).toUpperCase()||''
 function choose(next:File|null){
  if(!next||busy||!data)return
  setFile(null);setFileError('');setError('')
  if(!next.name.toLowerCase().endsWith(data.format.toLowerCase())){setFileError('请上传与原文相同的 '+format+' 文件。');return}
  if(!next.size||next.size>20_000_000){setFileError('文件不能为空，且不能超过 20 MB。');return}
  setFile(next)
 }
 function remove(){setFile(null);setFileError('');if(fileInput.current)fileInput.current.value=''}
 async function save(event:FormEvent){
  event.preventDefault();if(!data||!canSubmit)return
  setBusy(true);setError('')
  try{
   if(mode==='file'&&file){
    const body=new FormData();body.append('file',file);body.append('expected',String(data.expected));body.append('reason',reason.trim());body.append('declaration',String(declaration))
    const response=await fetch('/api/business/documents/'+id+'/correction-file',{method:'POST',credentials:'same-origin',headers:{'X-P18-Client':'workbench'},body})
    if(!response.ok){const result=await response.json();throw Error(typeof result.detail==='string'?result.detail:'提交失败，请重试。')}
   }else await api.post('/api/business/documents/'+id+'/correction',{expected:data.expected,reason:reason.trim(),declaration,paragraphs:changes.map(p=>({ordinal:p.ordinal,text:texts[p.ordinal]}))})
   onDone()
  }catch(e){setError((e as Error).message)}finally{setBusy(false)}
 }
 return <DocumentModal open title="轻量勘误" label="轻量勘误" busy={busy} onClose={onClose} description="只修正错别字或排版，文档版本保持不变。">
  <form className="correction-form" onSubmit={save}>
   {document&&<div className="correction-document"><FileText size={21}/><div><strong>{documentTitleParts(document.name).title}</strong><span>{document.version}{format&&' · '+format}</span></div></div>}
   {loadError?<div role="alert" className="correction-error">{loadError}<button type="button" onClick={()=>setAttempt(n=>n+1)}>重新读取</button></div>:!data?<p role="status" className="correction-loading">正在读取文档…</p>:<>
    <section className="correction-step" aria-label="修正内容"><h3><span>1</span>提供修正内容</h3>
     {data.paragraphs.some(p=>p.editable)&&<div className="correction-modes" role="group" aria-label="修正方式">{([['file','上传修正文件'],['text','直接修改正文']]as const).map(([value,label])=><button key={value} type="button" disabled={busy} aria-pressed={mode===value} onClick={()=>{setMode(value);setError('')}}>{label}</button>)}</div>}
     {mode==='file'?<>
      <label className={'correction-upload '+(drag?'is-dragging':'')} onDragOver={e=>{e.preventDefault();if(!busy)setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);if(e.dataTransfer.files.length!==1){setFile(null);setFileError('每次只提交一份修正文件。');return}choose(e.dataTransfer.files[0])}}>
       <input ref={fileInput} className="sr-only" aria-label="勘误原稿" type="file" accept={data.format} disabled={busy} onChange={e=>choose(e.target.files?.[0]||null)}/>
       <CloudUpload size={26}/><strong>{file?'点击更换文件':'拖入修正文件，或点击选择'}</strong><span>仅限 {format} · 最大 20 MB</span>
      </label>
      {file&&<div className="correction-file"><Check size={17}/><div><strong>{file.name}</strong><span>{(file.size/1024).toFixed(1)} KB · 尚未提交</span></div><button type="button" aria-label="移除修正文件" disabled={busy} onClick={remove}><X size={16}/></button></div>}
      {fileError&&<p role="alert" className="correction-error">{fileError}</p>}
     </>:<><p className="correction-hint">适用于普通段落；表格、图片和复杂排版请改用上传文件。</p><div className="correction-paragraphs">{data.paragraphs.map(p=><label key={p.ordinal}><span>段落 {p.ordinal+1}{!p.editable?' · 此段不可直接编辑':''}</span><textarea aria-label={'段落 '+(p.ordinal+1)} disabled={busy||!p.editable} maxLength={50000} value={texts[p.ordinal]??p.text} onChange={e=>setTexts({...texts,[p.ordinal]:e.target.value})}/></label>)}</div><p className="correction-hint">已修改 {changes.length} 个段落。修改后的局部字形可能重排。</p></>}
    </section>
    <section className="correction-step"><h3><span>2</span>说明修改之处</h3><label className="correction-reason"><span className="sr-only">勘误原因</span><textarea aria-label="勘误原因" required disabled={busy} maxLength={2000} placeholder="例如：第 3 页“设各编号”改为“设备编号”，并调整表格对齐。" value={reason} onChange={e=>setReason(e.target.value)}/></label></section>
    <section className="correction-step correction-confirm"><h3><span>3</span>确认修改范围</h3><label><input type="checkbox" disabled={busy} required checked={declaration} onChange={e=>setDeclaration(e.target.checked)}/><span>我确认仅修正错别字或排版，未改变核心参数和业务事实。</span></label><p>检查通过后自动生效，期间旧内容继续可用；发现内容风险时转入审核。</p></section>
    <details className="correction-rules"><summary>什么情况应该上传新版本？</summary><p>参数、流程、结论等业务内容发生变化时，请退出此页，从“上传资料”提交新版本。系统不会仅凭声明判断修改性质，原文件、修正文件、修改说明和操作人都会留存。</p></details>
   </>}
   {error&&<p role="alert" className="correction-error">{error}</p>}
   <div className="dm-modal-actions"><span className="correction-footnote">原稿与操作记录保留</span><button type="button" className="correction-cancel" disabled={busy} onClick={onClose}>取消</button><button type="submit" className="dm-primary" disabled={!canSubmit}>{busy?'正在提交…':'提交修正'}</button></div>
  </form>
 </DocumentModal>
}

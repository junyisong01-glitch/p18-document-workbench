import {useEffect,useRef,useState,type ReactNode} from 'react'
import {CloudUpload,FileText,X} from 'lucide-react'
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog'
import './DocumentLayout.css'
import './DocumentInteractions.css'

export function DocumentFormat({format,secret=false,legacy=false}:{format:string;secret?:boolean;legacy?:boolean}){
 return <span aria-label={'文件格式 '+format} className={'dm-format '+(secret?'dm-format-secret':legacy?'dm-format-legacy':'')}>{format||'文件'}</span>
}
export function DocumentViews({tabs,active,counts,loaded,onSelect}:{tabs:string[];active:string;counts:Record<string,number>;loaded:boolean;onSelect:(tab:string)=>void}){
 const groups=[{name:'流转',items:['已发布','我的提交']},{name:'待办',items:['解析异常','内容待审','待发布']},{name:'库',items:['历史归档','已下架','回收站']},{name:'管理',items:['人员职责','邀请建号']}]
 return <nav aria-label="业务流程视图" className="dm-view-groups">{groups.map(group=>{const items=group.items.filter(item=>tabs.includes(item));return items.length?<fieldset key={group.name}><legend>{group.name}</legend>{items.map(item=><button type="button" aria-label={item} aria-pressed={active===item} className={active===item?'active':''} key={item} onClick={()=>onSelect(item)}>{item}{item in counts&&<span aria-hidden="true" className={group.name==='待办'?'dm-count-pending':''}>{loaded?counts[item]:'…'}</span>}</button>)}</fieldset>:null})}</nav>
}
export function BusinessFilePicker({file,busy,onFile,onError}:{file:File|null;busy:boolean;onFile:(file:File|null)=>void;onError:(message:string)=>void}){
 const ref=useRef<HTMLInputElement>(null),[drag,setDrag]=useState(false)
 useEffect(()=>{if(!file&&ref.current)ref.current.value=''},[file])
 function pick(next:File|null){if(!next||busy)return;if(!/\.(docx?|xlsx?|pdf|txt|md|csv|jpe?g|png)$/i.test(next.name)){onError('支持 PDF / Word / Excel / TXT / Markdown / CSV / JPG / PNG，请重新选择。');return}onError('');onFile(next)}
 return <div className="dm-file-picker"><label className={'dm-upload-area '+(drag?'dragging':'')} onDragOver={event=>{event.preventDefault();if(!busy)setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={event=>{event.preventDefault();setDrag(false);pick(event.dataTransfer.files[0]||null)}}>
  <input ref={ref} type="file" aria-label="业务文件" accept=".doc,.docx,.xlsx,.xls,.pdf,.txt,.md,.csv,.jpg,.jpeg,.png" disabled={busy} className="sr-only" onChange={event=>pick(event.target.files?.[0]||null)}/><CloudUpload size={25} aria-hidden="true"/><strong>{file?'更换已选文件':'点击选择或拖拽文件到这里'}</strong><span>PDF / Word / Excel / TXT / Markdown / CSV / JPG / PNG · 提交后由服务端解析</span>
 </label>{file&&<div className="dm-picked-file"><FileText size={22}/><div><strong>{file.name}</strong><span>{(file.size/1024).toFixed(1)} KB · 已选择，尚未提交</span></div><button type="button" disabled={busy} aria-label="移除已选文件" onClick={()=>onFile(null)}><X size={16}/></button></div>}</div>
}
export function DocumentModal({open,title,label,description,busy=false,onClose,children}:{open:boolean;title:string;label?:string;description:string;busy?:boolean;onClose:()=>void;children:ReactNode}){
 return <Dialog open={open} onOpenChange={value=>{if(!value&&!busy)onClose()}}><DialogContent aria-labelledby={undefined} aria-label={label||title} className="dm-modal sm:max-w-2xl" showCloseButton={!busy} onEscapeKeyDown={event=>{if(busy)event.preventDefault()}} onPointerDownOutside={event=>{if(busy)event.preventDefault()}}><DialogHeader><span className="dm-kicker">DOCUMENT WORKFLOW</span><DialogTitle>{title}</DialogTitle><DialogDescription>{description}</DialogDescription></DialogHeader>{children}</DialogContent></Dialog>
}

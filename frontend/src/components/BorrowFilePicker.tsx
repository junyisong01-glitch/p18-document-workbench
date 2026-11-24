import {useState,type RefObject} from 'react'
import {Check,FileText,Search} from 'lucide-react'
import {Dialog,DialogContent,DialogTitle,DialogDescription} from './ui/dialog'
import {documentTitleParts} from '@/lib/document-title'
import type {BusinessRow} from './BusinessPresentation'

type Group={category:string;items:BusinessRow[]}
const titleOf=(doc:BusinessRow)=>documentTitleParts(doc.name).title.replace(/\s+[vV]\d+(?:\.\d+)*$/,'')

export function BorrowFilePicker({groups,department,value,onSelect,onClose,returnFocus}:{groups:Group[];department:string;value:string[];onSelect:(ids:string[])=>void;onClose:()=>void;returnFocus:RefObject<HTMLButtonElement|null>}){
 const [query,setQuery]=useState(''),[category,setCategory]=useState(''),[draft,setDraft]=useState(value)
 const all=groups.flatMap(group=>group.items),chosen=all.filter(doc=>draft.includes(doc.id))
 const term=query.trim().toLocaleLowerCase()
 const visible=groups.filter(group=>!category||group.category===category).map(group=>({...group,items:group.items.filter(doc=>[doc.name,doc.code,doc.docType,doc.version].join(' ').toLocaleLowerCase().includes(term))})).filter(group=>group.items.length)
 const count=visible.reduce((sum,group)=>sum+group.items.length,0)
 return <Dialog open onOpenChange={open=>{if(!open)onClose()}}><DialogContent className="borrow-picker sm:max-w-3xl" onCloseAutoFocus={event=>{event.preventDefault();returnFocus.current?.focus()}}>
  <header className="borrow-picker-header"><DialogTitle>选择借阅文件</DialogTitle><DialogDescription>从可授权的资料中选择所需文件（可多选），确认后返回申请。</DialogDescription><div className="access-picker-scope"><span>{department}</span><small>仅显示已发布且可授权的资料 · {all.length} 份</small></div></header>
  <label className="borrow-picker-search"><Search size={17} aria-hidden="true"/><input aria-label="搜索借阅文件" placeholder="搜索文件名称或编号" value={query} onChange={event=>setQuery(event.target.value)}/>{query&&<button type="button" onClick={()=>setQuery('')}>清空</button>}</label>
  <div className="borrow-picker-body"><nav className="borrow-picker-categories" aria-label="文档分类"><button type="button" aria-pressed={!category} onClick={()=>setCategory('')}>全部资料<span>{all.length}</span></button>{groups.map(group=><button key={group.category} type="button" aria-pressed={category===group.category} onClick={()=>setCategory(group.category)}>{group.category}<span>{group.items.length}</span></button>)}</nav>
   <div className="borrow-picker-results"><p className="borrow-picker-count" role="status">{term?`找到 ${count} 份资料`:`${category||'全部资料'} · ${count} 份`}</p>{visible.length?visible.map(group=><section key={group.category} aria-label={group.category}><h3>{group.category}<span>{group.items.length}</span></h3>{group.items.map(doc=><button key={doc.id} type="button" className="borrow-picker-file" aria-pressed={draft.includes(doc.id)} onClick={()=>setDraft(ids=>ids.includes(doc.id)?ids.filter(id=>id!==doc.id):[...ids,doc.id])}><FileText size={19} aria-hidden="true"/><span><strong title={doc.name}>{titleOf(doc)}</strong><small>{doc.version||'未标注版本'} · {doc.format?.toUpperCase()||'文档'}</small></span><i aria-hidden="true">{draft.includes(doc.id)&&<Check size={13}/>}</i></button>)}</section>):<div className="borrow-picker-empty"><Search size={24} aria-hidden="true"/><strong>{term?'没有匹配的文件':'暂无可选择的文件'}</strong><p>{term?'试试其他关键词，或切换到全部资料。':'该部门暂无可授权的已发布资料。'}</p></div>}</div>
  </div>
  <footer className="borrow-picker-footer"><div aria-live="polite"><small>{chosen.length?`已选择 ${chosen.length} 份文件`:'尚未选择文件'}</small><strong title={chosen.map(doc=>doc.name).join('、')}>{chosen.length?chosen.map(titleOf).join('、'):'请选择本次借阅需要的资料'}</strong></div><div><button type="button" className="borrow-picker-cancel" onClick={onClose}>取消</button><button type="button" className="dm-primary" disabled={!chosen.length} onClick={()=>onSelect(chosen.map(doc=>doc.id))}>确认选择</button></div></footer>
 </DialogContent></Dialog>
}

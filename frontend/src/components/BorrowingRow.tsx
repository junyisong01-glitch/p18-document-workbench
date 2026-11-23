import {ArrowUpRight} from 'lucide-react'
import {DocumentFormat} from './DocumentLayout'
import type {BusinessRow} from './BusinessPresentation'
import {demoIdentityName} from '@/lib/demo-identity-names'
import {documentTitleParts} from '@/lib/document-title'
import './BorrowingRow.css'

export function BorrowingRow({row,busy,preview,audit,revoke}:{row:BusinessRow;busy:boolean;preview:()=>void;audit:()=>void;revoke:(username:string)=>void}){
 const people=row.active_borrowings||[]
 return <article className="dm-borrowing-row" data-document-id={row.id}>
  <header><DocumentFormat format={row.format} secret={row.workflow.restricted}/><div className="dm-borrowing-document"><div className="dm-title-line"><button className="dm-document-title" onClick={preview}>{documentTitleParts(row.name).title}</button><span className="dm-version">{row.version}</span></div><p>{row.department}<span>借给 {people.length} 人</span></p></div><button className="dm-borrowing-audit" onClick={audit}>操作记录<ArrowUpRight size={14}/></button></header>
  <div className="dm-borrowers" aria-label="当前借阅人">{people.map(person=><div className="dm-borrower" key={person.username}><span className="dm-borrower-avatar" aria-hidden="true">{(demoIdentityName(person.username)||person.username).slice(0,1)}</span><div className="dm-borrower-name"><strong>{demoIdentityName(person.username)||person.username}</strong><span>{person.department||'未分配部门'} · {person.username}</span></div><div className="dm-borrowing-term"><span>借阅有效</span><small>{person.expires_at?'有效至 '+new Date(person.expires_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}):'未设置到期时间'}</small></div><button className="dm-borrowing-revoke" disabled={busy} onClick={()=>revoke(person.username)} aria-label={'撤销 '+(demoIdentityName(person.username)||person.username)+' 的借阅'}>撤销借阅</button></div>)}</div>
 </article>
}

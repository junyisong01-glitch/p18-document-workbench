import {useState,type ReactNode} from 'react'
import {Info} from 'lucide-react'
import './QaAnswerActions.css'

export function QaAnswerActions({provider,children}:{provider?:string;children:ReactNode}){
 const [expanded,setExpanded]=useState(false)
 const external=provider?.includes('DeepSeek')
 return <div className="qa-answer-actions">
  {children}
  {external&&<span className="qa-answer-external">DeepSeek · 外部参考回答</span>}
  {provider&&<button type="button" className="qa-answer-action" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}><Info size={14}/><span>回答说明</span></button>}
  {provider&&expanded&&<div className="qa-answer-explanation"><p>{provider==='本地证据核对'?'本轮使用本地证据核对。':external?'本轮使用外部模型生成参考回答。':provider.includes('Ollama')||provider.includes('本地')?'本轮使用本地模型生成回答。':'本轮回答服务：'+provider}</p><p>请结合引用资料核对关键内容；发现问题可提交反馈。</p></div>}
 </div>
}

import {useState,type ReactNode} from 'react'
import {Info} from 'lucide-react'
import './QaAnswerActions.css'

export function QaAnswerActions({provider,children,insufficientEvidence=false}:{provider?:string;children:ReactNode;insufficientEvidence?:boolean}){
 const [expanded,setExpanded]=useState(false)
 const external=provider?.includes('DeepSeek')
 return <div className={'qa-answer-actions'+(insufficientEvidence?' qa-empty-actions':'')}>
  {children}
  {external&&!insufficientEvidence&&<span className="qa-answer-external">DeepSeek · 外部参考回答</span>}
  {(provider||insufficientEvidence)&&<button type="button" className="qa-answer-action" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}><Info size={14}/><span>回答说明</span></button>}
  {(provider||insufficientEvidence)&&expanded&&<div className="qa-answer-explanation">{insufficientEvidence?<p>本次只检索当前账号可查看的已发布资料。未找到依据，不等于整个知识库没有相关内容；是否需要借阅或补充资料，可由相关部门核查。</p>:<><p>{provider==='本地证据核对'?'本轮使用本地证据核对。':external?'本轮使用外部模型生成参考回答。':provider?.includes('Ollama')||provider?.includes('本地')?'本轮使用本地模型生成回答。':'本轮回答服务：'+provider}</p><p>请结合引用资料核对关键内容；发现问题可提交反馈。</p></>}</div>}
 </div>
}

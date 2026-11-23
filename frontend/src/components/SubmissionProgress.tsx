import {Check, Circle, CircleAlert, CircleDot, CircleMinus} from 'lucide-react'
import type {BusinessRow} from './BusinessPresentation'
import {submissionProgress} from '../lib/document-workflow'
import './SubmissionProgress.css'

export function SubmissionProgress({row}:{row:BusinessRow}){
 const steps=submissionProgress(row)
 return <ol className="submission-progress" aria-label="提交进度">
   {steps.map((step,i)=>{
     const Icon={done:Check,current:CircleDot,waiting:Circle,error:CircleAlert,stopped:CircleMinus}[step.state]
     return <li key={i} className={'submission-step is-'+step.state} aria-current={['current','error','stopped'].includes(step.state)&&!steps.slice(i+1).some(s=>s.state==='current')?'step':undefined}>
       <span className="submission-step-content"><Icon size={16} strokeWidth={1.8} aria-hidden="true"/><span>{step.label}</span><span className="sr-only">{step.state==='done'?'，已完成':step.state==='waiting'?'，尚未进行':''}</span></span>
       {i<steps.length-1&&<span className="submission-step-line" aria-hidden="true"/>}
     </li>
   })}
 </ol>
}

import {useState} from 'react'
import {Dialog,DialogContent,DialogDescription,DialogHeader,DialogTitle} from './ui/dialog'
import './QaModelRoute.css'

export function QaModelRoute({local,ready,supported,qichen,busy,onChange,questionOnly=false,externalEnabled=false}:{local:boolean;ready:boolean;supported:boolean;qichen:boolean;busy:boolean;questionOnly?:boolean;externalEnabled?:boolean;onChange:(provider:'ollama'|'deepseek')=>Promise<void>}){
 const [open,setOpen]=useState(false),[confirmed,setConfirmed]=useState(false),[error,setError]=useState('')
 const unavailable=questionOnly&&!externalEnabled?'系统级外部模型已关闭':qichen?'启辰库禁止向外部模型发送资料':!supported?'当前部署暂不支持页面切换模型':''
 async function change(provider:'ollama'|'deepseek'){
  setError('')
  try{await onChange(provider);setOpen(false);setConfirmed(false)}catch(error){setError((error as Error).message)}
 }
 return <div className="qr-control"><div className="qr-segments" role="group" aria-label="选择回答模型">
  <button type="button" aria-pressed={ready&&local} disabled={!ready||busy||!local&&!supported} onClick={()=>{if(!local)void change('ollama')}}>本地 Ollama</button>
  <span title={unavailable||undefined} tabIndex={unavailable?0:undefined}><button type="button" aria-pressed={ready&&!local&&!qichen} disabled={!ready||busy||!!unavailable} onClick={()=>{if(local){setConfirmed(false);setError('');setOpen(true)}}}>DeepSeek 接口</button></span>
 </div>{qichen&&<p className="qr-note">启辰资料仅本地处理，DeepSeek 不可选</p>}{!qichen&&<p className="qr-note">{questionOnly?(externalEnabled?(local?'默认本地 · 可选外部参考':'本次登录已选择外部参考 · 每轮重新核对'):'默认本地 · 外部模型已关闭'):'切换后须重新检索和确认；配置不会发送资料'}</p>}{!open&&error&&<p className="qr-error" role="alert">{error}</p>}
 <Dialog open={open} onOpenChange={value=>{if(!busy){setOpen(value);if(!value)setConfirmed(false)}}}><DialogContent aria-labelledby={undefined} aria-label="选择DeepSeek接口" className="qr-dialog" showCloseButton={!busy} onEscapeKeyDown={event=>{if(busy)event.preventDefault()}} onPointerDownOutside={event=>{if(busy)event.preventDefault()}}><DialogHeader><DialogTitle>选择 DeepSeek 接口</DialogTitle><DialogDescription>DeepSeek 是外部服务。此操作只更改本次登录的回答模型，不发送问题或文档，也不影响其他账号。</DialogDescription></DialogHeader>
 <p className="qr-warning">{questionOnly?'只有本轮所有命中资料均为对外公开，才可另行确认向 DeepSeek 发送问题。资料原文和历史始终在本地。':'切换后，旧证据和发送确认将失效。需要重新选择已获外发许可的演示资料，核对完整消息，并逐轮确认发送。启辰资料仍禁止外发。'}</p>
 <label className="qr-consent"><input type="checkbox" checked={confirmed} disabled={busy} onChange={event=>setConfirmed(event.target.checked)}/>我确认选择外部 DeepSeek，后续仍按许可与人工确认流程发送。</label>
 {error&&<p className="qr-error" role="alert">{error}</p>}<footer><button type="button" disabled={busy} onClick={()=>{setOpen(false);setConfirmed(false)}}>取消</button><button type="button" className="qr-primary" disabled={busy||!confirmed} onClick={()=>void change('deepseek')}>{busy?'正在切换…':'确认切换'}</button></footer></DialogContent></Dialog>
 </div>
}

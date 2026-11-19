// 复用现有品牌样式；模型与地址由服务端锁定，Key仅交给会话内存接口。
import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, Eye, EyeOff, Loader2, PlugZap, Trash2, X } from 'lucide-react'
import { clearModelKey, loadModelConfig, saveModelKey, type ModelConfigStatus } from '@/lib/modelConfig'

const inputClass='h-11 w-full rounded-md border border-input bg-card px-3 text-[13px] outline-none transition-colors duration-200 focus:border-[hsl(12_74%_42%)] focus:ring-2 focus:ring-[hsl(12_74%_42%/0.18)]'
const buttonClass='inline-flex items-center justify-center gap-2 rounded-md border border-border px-4 py-2.5 text-[12px] transition-colors duration-200 hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] disabled:cursor-not-allowed disabled:opacity-50'

export function ModelConfigDialog({open,onClose,onStatus,onChanged}: {
  open:boolean
  onClose:()=>void
  onStatus:(status:ModelConfigStatus)=>void
  onChanged:()=>void
}) {
  const [status,setStatus]=useState<ModelConfigStatus|null>(null)
  const [apiKey,setApiKey]=useState(''),[showKey,setShowKey]=useState(false)
  const [busy,setBusy]=useState(false),[loading,setLoading]=useState(false)
  const [error,setError]=useState(''),[notice,setNotice]=useState('')
  const dialog=useRef<HTMLDivElement>(null),keyInput=useRef<HTMLInputElement>(null)
  const busyRef=useRef(false)

  useEffect(()=>{
    let active=true
    setApiKey('');setShowKey(false);setError('');setNotice('');setStatus(null)
    if(open){
      setLoading(true)
      loadModelConfig().then(next=>{if(active){setStatus(next);onStatus(next)}})
        .catch(()=>{if(active)setError('无法读取当前模型配置，请关闭后重开。本地检索仍可使用。')})
        .finally(()=>{if(active)setLoading(false)})
    }
    return()=>{active=false}
  },[open,onStatus])

  useEffect(()=>{
    if(!open)return
    const previous=document.activeElement as HTMLElement|null
    keyInput.current?.focus()
    function onKey(event:KeyboardEvent){
      if(event.key==='Escape'){
        event.preventDefault();event.stopImmediatePropagation()
        if(!busyRef.current)onClose()
      }
      if(event.key==='Tab'){
        const elements=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not([disabled]),input:not([disabled]),[href]')||[])
        const first=elements[0],last=elements.at(-1)
        if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}
        else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}
      }
    }
    window.addEventListener('keydown',onKey,true)
    return()=>{window.removeEventListener('keydown',onKey,true);if(previous?.isConnected)previous.focus()}
  },[open,onClose])

  if(!open)return null
  const keyValid=/^[A-Za-z0-9_-]{16,256}$/.test(apiKey.trim())
  async function change(clear=false){
    if(busyRef.current||!status||(!clear&&!keyValid))return
    busyRef.current=true;setBusy(true);setError('');setNotice('')
    try{
      if(clear)await clearModelKey();else await saveModelKey(apiKey)
      // 原生后端会销毁旧票据，界面也必须撤下已有确认预览。
      onChanged()
      const next={...status,configured:!clear};setStatus(next);onStatus(next)
      setNotice(clear?'已清除本次登录的Key，旧发送确认已失效。':'已保存本次登录配置，未向DeepSeek发送验证请求。请重新预览确认后再问答。')
    }catch{
      // 不显示可能包含输入正文的第三方异常；服务端也不会回显Key。
      setError('配置操作未完成。请检查Key格式及登录状态；问答正在进行时不能修改配置。')
    }finally{setApiKey('');setShowKey(false);setBusy(false);busyRef.current=false}
  }

  async function check(){
    if(busyRef.current)return
    setError('');setNotice('')
    if(apiKey.trim()&&!keyValid){setError('Key应为16—256位字母、数字、下划线或连字符，请核对后再保存。');return}
    busyRef.current=true;setBusy(true)
    try{
      const next=await loadModelConfig();setStatus(next);onStatus(next)
      setNotice('本地配置与会话检查完成。未连接模型服务，未验证Key有效性或余额，也未发送文档。')
    }catch{setError('无法检查本地模型配置，请核对登录状态或稍后重新打开。')}
    finally{setBusy(false);busyRef.current=false}
  }

  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-[hsl(36_16%_9%/0.55)] p-4 backdrop-blur-[2px]" onClick={()=>{if(!busy)onClose()}}>
    <div ref={dialog} role="dialog" aria-modal="true" aria-labelledby="model-config-title" aria-describedby="model-config-description" aria-busy={busy||loading} className="flex max-h-[90vh] w-full max-w-xl flex-col border border-border bg-card shadow-2xl" onClick={event=>event.stopPropagation()}>
      <header className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
        <div><div className="kicker">Model Endpoint</div><h2 id="model-config-title" className="mt-2 font-display text-[20px] font-semibold">模型接口配置</h2><p id="model-config-description" className="mt-2 text-[12px] leading-relaxed text-muted-foreground">由P18后端调用当前核准的模型接口；配置本身不会产生模型请求。</p></div>
        <button className={buttonClass+' border-transparent p-2'} aria-label="关闭模型配置" disabled={busy} onClick={onClose}><X className="size-4"/></button>
      </header>
      <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-6 py-5">
        <section><h3 className="mb-2 text-[13px] font-medium">当前接入服务</h3><div className="rounded-md border border-[hsl(12_74%_42%/0.45)] bg-[hsl(12_74%_42%/0.04)] px-4 py-3 text-[13px] font-semibold text-[hsl(12_74%_38%)]">{status?.provider||'正在读取服务配置…'}</div><p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">接口与模型由当前部署锁定，暂不支持在页面切换OpenAI、Kimi或自定义目标地址。</p></section>
        <div><label htmlFor="model-config-base" className="mb-2 block text-[13px] font-medium">接口地址 <span className="font-normal text-muted-foreground">· 后端配置</span></label><input id="model-config-base" readOnly value={status?.baseUrl||''} className={inputClass+' bg-secondary/35 font-mono2 text-muted-foreground'}/></div>
        <div><label htmlFor="model-config-key" className="mb-2 block text-[13px] font-medium">API Key <span className="text-[hsl(12_74%_42%)]">*</span></label><div className="relative"><input ref={keyInput} id="model-config-key" type={showKey?'text':'password'} value={apiKey} disabled={busy||loading} onChange={event=>{setApiKey(event.target.value);setError('');setNotice('')}} maxLength={256} autoComplete="off" autoCapitalize="none" spellCheck={false} placeholder={status?.configured?'已配置；重新填写可替换当前Key':'输入你自己的DeepSeek API Key'} className={inputClass+' pr-12 font-mono2'}/><button type="button" aria-label={showKey?'隐藏密钥':'显示密钥'} disabled={busy} onClick={()=>setShowKey(value=>!value)} className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-2 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]">{showKey?<EyeOff className="size-4"/>:<Eye className="size-4"/>}</button></div><p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{status?.configured?'本次登录已有Key，服务端不会回传原值。':'尚未配置Key，本地检索仍可使用。'}保存后输入框立即清空；配置不等于验证成功。</p></div>
        <div><label htmlFor="model-config-model" className="mb-2 block text-[13px] font-medium">模型名称 <span className="font-normal text-muted-foreground">· 当前实际值</span></label><input id="model-config-model" readOnly value={status?.model||''} className={inputClass+' bg-secondary/35 font-mono2 text-muted-foreground'}/></div>
        {loading&&<p role="status" className="text-[12px] text-muted-foreground">正在读取本地配置…</p>}
        {error&&<p role="alert" className="border-l-2 border-[hsl(12_74%_42%)] pl-3 text-[12px] leading-relaxed text-[hsl(12_74%_38%)]">{error}</p>}
        {notice&&<p role="status" className="flex gap-2 text-[12px] leading-relaxed text-[hsl(148_32%_28%)]"><CheckCircle2 className="mt-0.5 size-4 shrink-0"/>{notice}</p>}
        <p className="border-t border-dashed border-border pt-4 text-[11px] leading-[1.8] text-muted-foreground">Key仅保存在后端当前登录会话的临时内存，不写入浏览器存储或文件；刷新后当前会话仍可用，退出登录或服务重启后失效。问答仍须逐次核对外发许可、具体证据和接收地址，费用由你的API账户承担。未许可资料不会因配置Key而获准外发。</p>
      </div>
      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-6 py-4">
        <button className={buttonClass+' border-transparent text-muted-foreground'} disabled={busy||loading||!status?.configured} onClick={()=>change(true)}><Trash2 className="size-4"/>清除配置</button>
        <div className="flex gap-2"><button className={buttonClass} disabled={busy||loading} onClick={check}><PlugZap className="size-4"/>检查配置（不联网）</button><button className={buttonClass+' border-[hsl(12_74%_42%)] bg-[hsl(12_74%_42%)] font-semibold text-white hover:bg-[hsl(12_74%_38%)]'} disabled={busy||loading||!status||!keyValid} onClick={()=>change()}>{busy&&<Loader2 className="size-4 animate-spin"/>}保存配置</button></div>
      </footer>
    </div>
  </div>
}

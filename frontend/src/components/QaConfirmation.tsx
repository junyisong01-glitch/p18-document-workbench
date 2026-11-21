import {Monitor,Cloud,ChevronDown,Plus} from 'lucide-react'
import {parseConfirmation,isLocalAnswerEndpoint,endpointHost,displayValue,type WireSource} from '../lib/confirmation-presentation'
import './QaConfirmation.css'
import { documentTitleParts } from '../lib/document-title'

type Prepared = {
  messages:unknown;provider?:string;model?:string;request_endpoint?:string;configured?:boolean;
  budget?:{message_chars?:number;context_limit?:number;message_bytes?:number;byte_limit?:number}
}
function SourceMeta({source}:{source:WireSource}){
  return <p className="qc-source-meta">{[documentTitleParts(source.document_name||'').number,displayValue(source.section),source.revision!==undefined?`正文修订 ${source.revision}`:''].filter(Boolean).join(' · ')}</p>
}
function Risk({value}:{value:unknown}){
  const text=displayValue(value)
  return text&&text!=='[]'&&text!=='{}'?<p className="qc-risk">来源提示：{text}</p>:null
}
function SourceGroup({source,index}:{source:WireSource;index:number}){
  return <details className="qc-source"><summary><span className="qc-source-id">{source.id||`来源 ${index+1}`}</span><div className="qc-source-copy"><h3>{documentTitleParts(source.document_name||'参考片段').title}</h3><SourceMeta source={source}/></div><span className="qc-source-toggle">查看片段<ChevronDown aria-hidden="true" size={13}/></span></summary><div className="qc-excerpt"><p className="qc-caption">本轮实际使用的完整片段</p><pre className="qc-readable" data-wire-text="group">{source.text}</pre><Risk value={source.risk}/>{!!source.members?.length&&<section className="qc-members" aria-label="组内全部来源"><h4>组内全部来源 · {source.members.length} 段</h4>{source.members.map((member,j)=><article key={j}><p className="qc-member-name">{j+1}. {documentTitleParts(member.document_name||source.document_name||'组内来源').title}</p><SourceMeta source={member.document_name?member:{...member,document_name:source.document_name}}/>{member.text===undefined||member.text===source.text?<p className="qc-caption">与上方共享同一完整片段。</p>:<pre className="qc-readable" data-wire-text="member">{member.text}</pre>}<Risk value={member.risk}/></article>)}</section>}</div></details>
}
export function QaConfirmation({pending,consent,busy,onConsent,onSend,onCancel,privateDeployment=false}:{
  pending:Prepared;consent:boolean;busy:boolean;onConsent:(value:boolean)=>void;onSend:()=>void;onCancel:()=>void;privateDeployment?:boolean
}){
  const outbound = Array.isArray(pending.messages) && pending.messages.length===1 && pending.request_endpoint==='https://api.deepseek.com/chat/completions' && pending.messages[0]?.role==='user' && typeof pending.messages[0]?.content==='string' ? pending.messages[0].content : null
  if(outbound!==null) return <section id="qa-final-confirmation" role="dialog" aria-label="最终发送确认" className="qc-panel">
    <header className="qc-header"><span className="qc-step">3</span><div><h2>确认本次外发问题</h2><p>DeepSeek 提供外部参考回答。</p></div></header>
    <div className="qc-body"><section className="qc-question"><h3>本次问题</h3><p>{outbound}</p></section>
      <p className="qc-external-warning">接收方 api.deepseek.com · 发送内容仅为以上问题。</p>
      <details className="qc-advanced"><summary>查看本次外发内容</summary><pre className="qc-raw">{JSON.stringify(pending.messages,null,2)}</pre></details></div>
    <footer className="qc-footer"><label className="qc-consent"><input type="checkbox" checked={consent} disabled={busy||!pending.configured} onChange={event=>onConsent(event.target.checked)}/>我同意仅将本次问题发送给 DeepSeek。</label>
      <div className="qc-actions"><button type="button" className="qc-primary" disabled={!consent||busy||!pending.configured} onClick={onSend}>确认发送</button><button type="button" className="qc-back" disabled={busy} onClick={onCancel}>返回调整</button></div></footer></section>
  const content=parseConfirmation(pending.messages),local=isLocalAnswerEndpoint(pending.request_endpoint)
  const host=endpointHost(pending.request_endpoint),budget=pending.budget
  return <section id="qa-final-confirmation" role="dialog" aria-label="最终发送确认" className="qc-panel">
    <header className="qc-header"><span className="qc-step">3</span><div><h2>确认问题与参考资料</h2><p>核对本轮使用的内容，确认后再{local?'生成回答':'发送'}。修改问题、证据或配置后需重新确认。</p></div></header>
    <div className="qc-body">
      {content&&<section className="qc-question"><h3>本次问题</h3><p>{content.question}</p></section>}
      <section className={'qc-destination '+(local?'qc-local':'qc-external')} aria-label="本次处理位置">
        <span className="qc-device">{local?<Monitor aria-hidden="true" size={23}/>:<Cloud aria-hidden="true" size={23}/>}</span>
        <div className="qc-destination-copy"><div className="qc-destination-heading"><strong>{local?(privateDeployment?'私有模型处理':'本机处理'):`外部服务 · ${pending.provider||host}`}</strong><span>{pending.provider} · {pending.model}</span></div><p>{local?(privateDeployment?'本轮问题和资料交给当前部署环境中的私有模型处理，不发送至外部模型服务。':'本轮问题和资料仅在这台电脑上处理，不发送至外部服务。'):`接收域名：${host}。本次外发仍须有效许可与人工确认。`}</p></div><span className="qc-location-badge"><i/>{local?'资料不外发':'需确认外发'}</span>
      </section>
      {!local&&<p className="qc-external-warning">确认后，将向 <strong>{host}</strong> 发送本次问题、以下参考资料{content?.history.length?'及本轮携带的历史对话':''}。公开可读不等于允许外发。</p>}
      {content?<>
        <section className="qc-evidence" aria-labelledby="qc-evidence-title"><header><h3 id="qc-evidence-title">本次参考资料 <span>{content.evidence.length} 组</span></h3><span>展开可核对完整片段</span></header>{content.evidence.map((source,index)=><SourceGroup source={source} index={index} key={index}/>)}</section>
        <div className="qc-secondary">
          {!!content.history.length&&<details><summary><Plus aria-hidden="true" size={14}/><span>本轮携带的历史对话</span><small>{content.history.length} 轮 · 仅辅助理解指代</small></summary><div className="qc-details-content"><pre className="qc-readable" aria-label="本轮完整历史对话">{JSON.stringify(content.history,null,2)}</pre></div></details>}
          <details><summary><Plus aria-hidden="true" size={14}/><span>模型回答规则</span><small>依据资料回答 · 无证据拒答 · 附来源</small></summary><div className="qc-details-content"><p className="qc-caption">以下是后端为本次请求准备的完整系统指令。</p>{content.systems.map((system,index)=><pre className="qc-readable" key={index}>{system}</pre>)}</div></details>
        </div>
      </>:<p role="status" className="qc-external-warning">本轮消息无法转换为分组视图，请展开下方完整请求核对；原始消息保留不变。</p>}
      <details className="qc-advanced" open={content?undefined:true}><summary><Plus aria-hidden="true" size={14}/><span>高级信息与完整请求</span><small>{budget?.message_chars!==undefined?`${budget.message_chars.toLocaleString()} 字符`:'查看原始消息'}</small></summary><div className="qc-details-content"><dl className="qc-technical"><div><dt>实际请求地址</dt><dd>{pending.request_endpoint||'未提供'}</dd></div><div><dt>完整消息容量</dt><dd>{budget?.message_chars??'—'} / {budget?.context_limit??'—'} 字符</dd></div>{budget?.byte_limit!==undefined&&<div><dt>本机保守容量校验</dt><dd>{budget.message_bytes} / {budget.byte_limit} UTF-8字节</dd></div>}</dl><p className="qc-caption">以下为后端实际准备提交给模型的完整消息。分组视图仅调整展示，未删减或修改请求内容。</p><pre aria-label="实际完整消息" className="qc-raw">{JSON.stringify(pending.messages,null,2)}</pre></div></details>
    </div>
    <footer className="qc-footer">
      {!pending.configured&&<p role="status" className="qc-risk">模型尚不可用。可以核对资料，生成前请检查{local?'本机模型服务':'模型配置'}。</p>}
      <label className="qc-consent"><input type="checkbox" disabled={!pending.configured||busy} checked={consent} onChange={event=>onConsent(event.target.checked)}/><span>{local?(privateDeployment?'我已核对本次问题和参考资料，同意由本部署的私有模型生成回答':'我已核对本次问题和参考资料，同意在本机生成回答'):'我已核对本次问题、参考资料及接收地址，同意本轮发送至 '+(pending.provider||host)}</span></label>
      <div className="qc-footer-row"><div className="qc-actions"><button className="qc-primary" disabled={!consent||!pending.configured||busy} onClick={onSend}>{busy?'正在生成…':local?'生成回答':'确认发送'}</button><button className="qc-back" disabled={busy} onClick={onCancel}>返回调整</button></div><p>{local?(privateDeployment?'私有模型处理 · 不调用外部模型API':'本机处理 · 问题与资料不外发'):'外部模型 · 仅发送本轮确认的内容'}</p></div>
    </footer>
  </section>
}

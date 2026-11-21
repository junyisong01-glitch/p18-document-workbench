import { useState, type FormEvent, type ReactNode, type RefObject } from 'react'
import { ArrowLeft, ArrowUp, PanelLeft, Plus, Settings2 } from 'lucide-react'
import { Link } from 'react-router'
import type { QaExample } from '@/lib/qa-examples'
import './QaWorkspace.css'

type WorkspaceProps = {
  library: string
  name: string
  role: string
  settings: ReactNode
  children: ReactNode
  history: { id: string; title: string }[]
  active: string | null
  hasTurns: boolean
  busy: boolean
  ready: boolean
  externalSelected: boolean
  question: string
  inputRef: RefObject<HTMLTextAreaElement | null>
  examples: QaExample[]
  onChange: (value: string) => void
  onAsk: (event: FormEvent) => void
  onNew: () => void
  onSelect: (id: string) => void
}

export function QaWorkspace(props: WorkspaceProps) {
  const [showHistory, setShowHistory] = useState(false)
  const {
    library, name, role, history, active, hasTurns, busy, ready, externalSelected, question, inputRef, examples,
    settings, onChange, onAsk, onNew, onSelect, children,
  } = props

  const composer = <form className={`qa-chat-composer ${hasTurns ? 'qa-chat-composer-follow' : ''}`} onSubmit={onAsk}>
    <textarea ref={inputRef} aria-label="问答问题" value={question} maxLength={2000} rows={hasTurns ? 1 : 2}
      placeholder={hasTurns ? '继续提问，回车发送…' : '输入你的问题…'} onChange={event => onChange(event.target.value)}
      onKeyDown={event => {
        if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229) return
        event.preventDefault()
        if (ready && !busy && question.trim()) event.currentTarget.form?.requestSubmit()
      }}/>
    <button type="submit" aria-label="检索证据" title="发送问题" disabled={!ready || busy || !question.trim()}>
      <ArrowUp size={20} strokeWidth={1.8}/>
    </button>
  </form>

  return <div className="qa-chat">
    <header className="qa-chat-header">
      <div className="qa-chat-brand">
        <button type="button" className="qa-chat-mobile qa-chat-icon" aria-expanded={showHistory}
          aria-controls="qa-conversation-history" aria-label="会话列表" onClick={() => setShowHistory(open => !open)}><PanelLeft size={19}/></button>
        <Link to="/" className="qa-chat-back" title="返回工作台" aria-label="返回工作台"><ArrowLeft size={17}/></Link>
        <span className="qa-chat-mark" aria-hidden="true">启</span>
        <strong>{library}</strong>
        <h1>知识问答</h1>
      </div>
      <div className="qa-chat-top-actions">
        <details className="qa-chat-settings">
          <summary title="模型设置"><Settings2 size={16}/><span>模型设置</span></summary>
          <div className="qa-chat-settings-panel">{settings}</div>
        </details>
        <Link to="/identity" className="qa-chat-user" title="权限与身份">
          <span aria-hidden="true">{Array.from(name)[0]}</span><b>{name}</b><small>· {role}</small>
        </Link>
      </div>
    </header>
    <div className="qa-chat-layout">
      <aside className={`qa-chat-side ${showHistory ? 'qa-chat-side-open' : ''}`} id="qa-conversation-history" aria-label={history.length ? '历史会话' : '会话'}>
        <button className="qa-chat-new" type="button" disabled={busy} onClick={() => { onNew(); setShowHistory(false) }}>
          <Plus size={16}/>新会话
        </button>
        {history.length > 0 && <>
          <h2>历史会话</h2>
          <ul>{history.map(item => <li key={item.id}>
            <button type="button" title={item.title} aria-current={item.id === active ? 'true' : undefined} disabled={busy}
              onClick={() => { onSelect(item.id); setShowHistory(false) }}>{item.title}</button>
          </li>)}</ul>
        </>}
      </aside>
      <main className="qa-chat-main">
        {hasTurns ? <>
          <div className="qa-chat-scroll"><div className="qa-chat-thread">{children}</div></div>
          <div className="qa-chat-dock">
            {composer}
            <p>{externalSelected ? '外部参考回答需逐轮确认' : '回答仅基于你有权查看的已发布资料'}</p>
          </div>
        </> : <div className="qa-chat-scroll">
          <section className="qa-chat-welcome" aria-label="开始提问">
            <h2>你好，<em>{name}</em></h2>
            <p>{externalSelected ? '可以检索获准资料。使用外部模型时，需要确认本轮问题。' : '有什么想查的？回答只来自知识库内已发布、且你有权查看的资料。'}</p>
            {composer}
            {examples.length > 0 && <div className="qa-first-chips" aria-label="示例问题">
              {examples.map(example => <button key={example.question} type="button" title={example.question}
                aria-label={`${example.label}：${example.question}`} onClick={() => { onChange(example.question); inputRef.current?.focus() }}>
                {example.label}
              </button>)}
            </div>}
            {!ready && children}
          </section>
        </div>}
      </main>
    </div>
  </div>
}

export function QaChatTurn({ question, children, anchor }: { question: string; children: ReactNode; anchor?: RefObject<HTMLElement | null> }) {
  return <section ref={anchor} className="qa-chat-turn">
    <p className="qa-chat-question">{question}</p>
    <div className="qa-chat-reply">
      <span className="qa-chat-mark" aria-hidden="true">启</span>
      <div className="qa-chat-message">{children}</div>
    </div>
  </section>
}

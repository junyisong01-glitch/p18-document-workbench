import { useEffect, useRef, useState, type CSSProperties, type FormEvent, type KeyboardEvent, type PointerEvent, type ReactNode, type RefObject } from 'react'
import { ArrowLeft, ArrowUp, PanelLeft, Plus, Settings2 } from 'lucide-react'
import { Link } from 'react-router'
import type { QaExample } from '@/lib/qa-examples'
import './QaWorkspace.css'

type WorkspaceProps = {
  onWidthChange?: (width: number) => void
  guest?: boolean
  library: string
  name: string
  role: string
  settings: ReactNode
  tools?: ReactNode
  preview?: ReactNode
  previewDocked?: boolean
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

const historyWidthKey = 'p18.qa.historyWidth'
const historyMinWidth = 176
const historyMaxWidth = 420
const historyDefaultWidth = 236
const clampHistoryWidth = (width: number) => Math.max(historyMinWidth, Math.min(historyMaxWidth, Math.round(width)))

function initialHistoryWidth() {
  try {
    const value = window.localStorage.getItem(historyWidthKey)
    if (value && Number.isFinite(Number(value))) return clampHistoryWidth(Number(value))
  } catch { /* Storage can be unavailable in restricted browser contexts. */ }
  return historyDefaultWidth
}

function saveHistoryWidth(width: number) {
  try {
    window.localStorage.setItem(historyWidthKey, String(width))
  } catch { /* Resizing still works for the current page. */ }
}

export function QaWorkspace(props: WorkspaceProps) {
  const workspace = useRef<HTMLDivElement>(null)
  const onWidthChange = props.onWidthChange
  useEffect(() => {
    const element = workspace.current
    if (!element || !onWidthChange) return
    const observer = new ResizeObserver(entries => onWidthChange(entries[0].contentRect.width))
    observer.observe(element)
    return () => observer.disconnect()
  }, [onWidthChange])
  const [showHistory, setShowHistory] = useState(false)
  const [historyWidth, setHistoryWidth] = useState(initialHistoryWidth)
  const [resizing, setResizing] = useState(false)
  const drag = useRef<{ id: number; startX: number; startWidth: number; width: number } | null>(null)
  const {
    library, name, role, history, active, hasTurns, busy, ready, externalSelected, question, inputRef, examples,
    settings, tools, preview, previewDocked, onChange, onAsk, onNew, onSelect, children,
  } = props

  function startResize(event: PointerEvent<HTMLDivElement>) {
    if (!event.isPrimary || event.button !== 0 || drag.current) return
    const handle = event.currentTarget
    event.preventDefault()
    handle.focus({ preventScroll: true })
    handle.setPointerCapture(event.pointerId)
    drag.current = { id: event.pointerId, startX: event.clientX, startWidth: historyWidth, width: historyWidth }
    setResizing(true)
  }

  function moveResize(event: PointerEvent<HTMLDivElement>) {
    const activeDrag = drag.current
    if (activeDrag?.id !== event.pointerId) return
    activeDrag.width = clampHistoryWidth(activeDrag.startWidth + event.clientX - activeDrag.startX)
    setHistoryWidth(activeDrag.width)
  }

  function finishResize(event: PointerEvent<HTMLDivElement>) {
    const activeDrag = drag.current
    if (activeDrag?.id !== event.pointerId) return
    drag.current = null
    saveHistoryWidth(activeDrag.width)
    setResizing(false)
  }

  function resizeWithKeyboard(event: KeyboardEvent<HTMLDivElement>) {
    const step = event.shiftKey ? 40 : 16
    const widths: Partial<Record<string, number>> = {
      ArrowLeft: historyWidth - step, ArrowRight: historyWidth + step, Home: historyMinWidth, End: historyMaxWidth,
    }
    const next = widths[event.key]
    if (typeof next !== 'number') return
    event.preventDefault()
    const width = clampHistoryWidth(next)
    setHistoryWidth(width)
    saveHistoryWidth(width)
  }

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

  return <div ref={workspace} className="qa-chat">
    <header className="qa-chat-header">
      <div className="qa-chat-brand">
        <button type="button" className="qa-chat-mobile qa-chat-icon" aria-expanded={showHistory}
          aria-controls="qa-conversation-history" aria-label="会话列表" onClick={() => setShowHistory(open => !open)}><PanelLeft size={19}/></button>
        {!props.guest&&<Link to="/workbench" className="qa-chat-back" title="返回工作台" aria-label="返回工作台"><ArrowLeft size={17}/></Link>}
        <span className="qa-chat-mark" aria-hidden="true">启</span>
        <strong>{library}</strong>
        <h1>知识问答</h1>
      </div>
      <div className="qa-chat-top-actions">
        {tools&&<nav className="flex items-center gap-4 text-xs text-muted-foreground" aria-label="问答快捷入口">{tools}</nav>}
        {settings&&<details className="qa-chat-settings">
          <summary title="模型设置"><Settings2 size={16}/><span>模型设置</span></summary>
          <div className="qa-chat-settings-panel">{settings}</div>
        </details>}
        {props.guest?<span className="qa-chat-user"><span aria-hidden="true">{Array.from(name)[0]}</span><b>{name}</b><small>· {role}</small></span>:<Link to="/identity" className="qa-chat-user" title="权限与身份"><span aria-hidden="true">{Array.from(name)[0]}</span><b>{name}</b><small>· {role}</small></Link>}

      </div>
    </header>
    <div className={`qa-chat-layout ${resizing ? 'qa-chat-layout-resizing' : ''} ${previewDocked ? 'qa-chat-layout-with-preview' : ''}`}
      style={{ '--qa-history-width': `${historyWidth}px` } as CSSProperties}>
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
      <div className="qa-chat-splitter" role="separator" tabIndex={0} aria-label="调整会话栏宽度"
        aria-controls="qa-conversation-history" aria-orientation="vertical" aria-valuemin={historyMinWidth}
        aria-valuemax={historyMaxWidth} aria-valuenow={historyWidth} aria-valuetext={`${historyWidth} 像素`}
        onPointerDown={startResize} onPointerMove={moveResize} onPointerUp={finishResize}
        onPointerCancel={finishResize} onLostPointerCapture={finishResize}
        onKeyDown={resizeWithKeyboard} />
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
      {preview}
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

import { Fragment, useRef, useState, type ReactNode } from 'react'
import { documentTitleParts } from '../lib/document-title'
import type { QaExample } from '../lib/qa-examples'
import type { Doc } from '../lib/types'
import { FileText, Lock } from 'lucide-react'
import { SearchEvidence } from './SearchEvidence'
import './QaAnswerFirst.css'

export type QaCitation = {
  id?: string
  document_id: string
  document_name: string
  chunk_id: string
  index_token: string
  revision: number
  section?: string
  text?: string
  members?: QaCitation[]
}

export type QaResult = {
  answer_status: string
  answer: string
  provider?: string
  citations?: QaCitation[]
}

type SuggestionsProps = { examples: QaExample[]; onAsk: (question: string) => void }

function Suggestions({ examples, onAsk }: SuggestionsProps) {
  return <div className="qa-first-chips">{examples.map(example =>
    <button key={example.question} type="button" onClick={() => onAsk(example.question)}>{example.question}</button>
  )}</div>
}

export function QaAnswerLoading({ phase }: { phase: 'search' | 'answer' }) {
  return <section className="qa-first-card qa-first-loading" role="status" aria-live="polite">
    <p className="sr-only">{phase === 'search' ? '正在检索可用资料…' : '正在生成回答…'}</p>
    <div className="qa-chat-dots" aria-hidden="true"><i/><i/><i/></div>
    <div className="qa-first-bars" aria-hidden="true"><i/><i/><i/><i/><i/></div>
  </section>
}

export function QaNoEvidence({ question, examples, onAsk }: SuggestionsProps & { question: string }) {
  return <section className="qa-first-card qa-first-empty" aria-label="没找到可靠依据" role="status">
    <h2>没找到可靠依据</h2>
    <p>当前可查阅的已发布资料中，暂未找到能回答「{question}」的依据。</p>
    <Suggestions examples={examples} onAsk={onAsk}/>
  </section>
}

type SourceEntry = { source: QaCitation; numbers: number[] }
type SourceGroup = { key: string; document: QaCitation; entries: Map<string, SourceEntry> }
type OpenSource = (source: QaCitation, view?: 'file') => void

function documentKey(source: QaCitation) {
  return JSON.stringify([source.document_id, source.revision, source.index_token])
}

function sourceKey(source: QaCitation) {
  return JSON.stringify([documentKey(source), source.chunk_id])
}

function groupSources(sources: QaCitation[], numbered: boolean) {
  const groups = new Map<string, SourceGroup>()
  sources.forEach((citation, index) => {
    for (const source of [citation, ...citation.members || []]) {
      const key = documentKey(source)
      let group = groups.get(key)
      if (!group) {
        group = { key, document: source, entries: new Map() }
        groups.set(key, group)
      }
      const entryKey = sourceKey(source)
      let entry = group.entries.get(entryKey)
      if (!entry) {
        entry = { source, numbers: [] }
        group.entries.set(entryKey, entry)
      }
      if (numbered && !entry.numbers.includes(index + 1)) entry.numbers.push(index + 1)
    }
  })
  return Array.from(groups.values())
}

function SourceRow({ entry, active, setNode, onSource, loadEvidence }: {
  entry: SourceEntry
  active?: boolean
  setNode?: (node: HTMLDetailsElement | null) => void
  onSource: (source: QaCitation) => void
  loadEvidence?: boolean
}) {
  const [expanded,setExpanded] = useState(false)
  const { source, numbers } = entry
  const section = source.section || '文档片段'
  return <div className="qa-chat-source-row" data-active={active || undefined}>
    <details ref={setNode} className="qa-first-source" onToggle={loadEvidence ? event => setExpanded(event.currentTarget.open) : undefined}>
      <summary>
        {numbers.length > 0 && <span className="qa-first-source-index">{numbers.map(number => '[' + number + ']').join(' ')}</span>}
        <strong>{section}</strong>
      </summary>
      {loadEvidence ? expanded && <div className="mt-2"><SearchEvidence documentId={source.document_id} sourceRef={source}/></div> :
        source.text && <blockquote>{source.text}</blockquote>}
    </details>
    <button className="qa-first-original" type="button" aria-label={`查看原文 ${section}`} onClick={() => onSource(source)}>查看原文</button>
  </div>
}

function SourceCard({ group, children, document, onSource }: {
  group: SourceGroup
  children: ReactNode
  document?: Doc
  onSource: OpenSource
}) {
  const { title, number } = documentTitleParts(group.document.document_name)
  return <section className="qa-chat-citation" aria-label={title}>
    <header className="qa-chat-source-header">
      <div>
        <h3>{title}</h3>
        {(number || document) && <div className="qa-chat-citation-meta">
          {number && <span>{number}</span>}
          {document?.version && <span>版本 {document.version}</span>}
          {document?.status === 'active' && <span className="qa-chat-published">已发布</span>}
        </div>}
      </div>
      <div className="qa-chat-source-actions">
        <span className="qa-chat-source-count">{group.entries.size} 个片段</span>
        <button type="button" className="qa-chat-open-file" onClick={() => onSource(group.document, 'file')}>
          <FileText size={14} aria-hidden="true"/>查看原文件
        </button>
      </div>
    </header>
    <div className="qa-chat-source-list">{children}</div>
  </section>
}

export function QaRelatedSources({ sources, onSource }: { sources: QaCitation[]; onSource: OpenSource }) {
  const groups = groupSources(sources, false)
  return <details className="qa-first-card" aria-label="本轮相关资料">
    <summary className="w-fit cursor-pointer text-sm font-medium">相关资料 {groups.length} 份</summary>
    <p className="my-3 text-xs text-muted-foreground">展开查看本轮命中的片段和原文。</p>
    {groups.map(group => <SourceCard key={group.key} group={group} onSource={onSource}>
      {Array.from(group.entries, ([key, entry]) => <SourceRow key={key} entry={entry} onSource={onSource} loadEvidence/>)}
    </SourceCard>)}
  </details>
}

const numberedLine = /^\s*(\d+)(?:[.][ \t]+|[、）)]\s*)/

function AnswerText({ text, cite }: { text: string; cite: (text: string) => ReactNode }) {
  // The server includes a trailing citation list. Inline links already
  // expose the same sources.
  const lines = text.replace(/\n来源片段：(\[S\d+\])+\s*$/, '').trim().split(/\n+/)
  const listStart = lines.findIndex(line => numberedLine.test(line))
  const isList = listStart >= 0 && lines.slice(listStart).every(line => numberedLine.test(line))
  const paragraphs = isList ? lines.slice(0, listStart) : lines
  if (paragraphs[0]?.length > 90) {
    const lead = /^(.{1,90}?[。！？](?:\s*\[S\d+\][。！？]?)*)\s*(?=\S)(?!\[S\d+\])/.exec(paragraphs[0])
    if (lead) paragraphs.splice(0, 1, lead[1], paragraphs[0].slice(lead[0].length))
  }
  return <>
    {paragraphs.map((line, index) =>
      index === 0 ? <p className="qa-first-lead" key={index}>{cite(line)}</p> : <p className="qa-first-paragraph" key={index}>{cite(line)}</p>
    )}
    {isList && <ol className="qa-first-list">{lines.slice(listStart).map((line, index) => {
      const prefix = numberedLine.exec(line)!
      return <li key={index} data-number={prefix[1]}><span>{cite(line.slice(prefix[0].length))}</span></li>
    })}</ol>}
  </>
}

export function QaAnswerFirst({ answer, examples, onAsk, onSource, notice, documents, guest }: SuggestionsProps & {
  answer: QaResult
  onSource: OpenSource
  notice?: string
  documents: Doc[]
  guest?: boolean
}) {
  const sources = useRef<HTMLDetailsElement>(null)
  const rows = useRef(new Map<string, HTMLDetailsElement>())
  const [activeSource, setActiveSource] = useState<string | null>(null)
  const positions = new Map(Array.from(new Set(answer.answer.match(/\[S\d+\]/g) || []), (id, index) => [id, index]))
  const order = (citation: QaCitation) => positions.get('[' + citation.id + ']') ?? Number.MAX_SAFE_INTEGER
  const citations = (answer.citations || []).slice().sort((first, second) => order(first) - order(second))
  const external = answer.provider?.includes('DeepSeek')
  const groups = groupSources(citations, true)

  function showCitation(index: number) {
    if (!sources.current) return
    const key = sourceKey(citations[index])
    sources.current.open = true
    const row = rows.current.get(key)
    if (!row) return
    row.open = true
    setActiveSource(key)
    row.querySelector('summary')?.focus({ preventScroll: true })
    row.scrollIntoView({ block: 'nearest' })
  }

  function cite(value: string): ReactNode {
    return value.split(/(\[S\d+\])/g).map((part, index) => {
      const citation = citations.findIndex(item => '[' + item.id + ']' === part)
      return citation < 0 ? <Fragment key={index}>{part}</Fragment> :
        <button className="qa-first-reference" type="button" key={index}
          aria-label={`展开来源 ${citation + 1}`} onClick={() => showCitation(citation)}>[{citation + 1}]</button>
    })
  }

  return <article className="qa-first-card" aria-label="本轮回答">
    {notice && <p className="qa-first-notice" role="status">{notice}</p>}
    <AnswerText text={answer.answer} cite={cite}/>
    {citations.length > 0 && <details className="qa-first-sources" ref={sources}>
      <summary>参考了 <strong>{groups.length} 份</strong> 资料</summary>
      {groups.map(group => <SourceCard group={group} key={group.key} onSource={onSource} document={documents.find(doc => doc.id === group.document.document_id)}>
        {Array.from(group.entries, ([key, entry]) => <SourceRow key={key} entry={entry} active={key === activeSource}
          setNode={node => { if (node) rows.current.set(key,node); else rows.current.delete(key) }}
          onSource={onSource}/>)}
      </SourceCard>)}
    </details>}
    {guest && !external && <p className="qa-chat-guest"><Lock size={13}/>内部资料需有权限的内部账号查看。</p>}
    {!!examples.length && <div className="qa-first-followup"><Suggestions examples={examples} onAsk={onAsk}/></div>}
    <p className="qa-chat-provider">{external ? 'DeepSeek · 外部参考回答' : '已使用本地模型'}</p>
  </article>
}

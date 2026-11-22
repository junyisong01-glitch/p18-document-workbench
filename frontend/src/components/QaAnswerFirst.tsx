import { Fragment, type ReactNode } from 'react'
import { documentTitleParts } from '../lib/document-title'
import type { QaExample } from '../lib/qa-examples'
import type { Doc } from '../lib/types'
import { Lock } from 'lucide-react'
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

export function QaNoEvidence({ question, examples, onAsk, onRecord }: SuggestionsProps & { question: string; onRecord?:()=>void }) {
  return <section className="qa-first-card qa-first-empty" aria-label="没找到可靠依据" role="status">
    <h2>没找到可靠依据</h2>
    <p>当前可查阅的已发布资料中，暂未找到能回答「{question}」的依据。</p>
    <Suggestions examples={examples} onAsk={onAsk}/>
    {onRecord&&<button type="button" onClick={onRecord} className="mt-5 rounded-full border border-border bg-card px-4 py-2 text-sm text-primary">记录未解决问题</button>}
  </section>
}

type OpenSource = (source: QaCitation) => void

export function citationLocations(citation: QaCitation) {
  const locations = new Map<string, QaCitation>()
  for (const source of [citation, ...citation.members || []]) {
    const key = JSON.stringify([source.document_id, source.revision, source.index_token, source.chunk_id])
    if (!locations.has(key)) locations.set(key, source)
  }
  return [...locations.values()]
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
  const positions = new Map(Array.from(new Set(answer.answer.match(/\[S\d+\]/g) || []), (id, index) => [id, index]))
  const order = (citation: QaCitation) => positions.get('[' + citation.id + ']') ?? Number.MAX_SAFE_INTEGER
  const citations = (answer.citations || []).slice().sort((first, second) => order(first) - order(second))
  const external = answer.provider?.includes('DeepSeek')
  const references = new Map<string, QaCitation>()
  for (const source of citations.flatMap(citationLocations)) {
    const key = JSON.stringify([source.document_id, source.revision])
    if (!references.has(key)) references.set(key, source)
  }

  function cite(value: string): ReactNode {
    return value.split(/(\[S\d+\])/g).map((part, index) => {
      const citation = citations.findIndex(item => '[' + item.id + ']' === part)
      return citation < 0 ? <Fragment key={index}>{part}</Fragment> :
        <button className="qa-first-reference" type="button" key={index}
          aria-label={`查看引用 ${citation + 1}`} onClick={() => onSource(citations[citation])}>[{citation + 1}]</button>
    })
  }

  return <article className="qa-first-card" aria-label="本轮回答">
    {notice && <p className="qa-first-notice" role="status">{notice}</p>}
    <AnswerText text={answer.answer} cite={cite}/>
    {references.size > 0 && <details className="qa-first-sources">
      <summary>参考了 <strong>{references.size} 份</strong> 资料</summary>
      <ul className="qa-first-document-list">
        {Array.from(references, ([key, source]) => {
          const document = documents.find(doc => doc.id === source.document_id)
          const { title } = documentTitleParts(source.document_name)
          return <li key={key}>
            {title}{document?.version && <span>版本 {document.version}</span>}
          </li>
        })}
      </ul>
    </details>}
    {guest && !external && <p className="qa-chat-guest"><Lock size={13}/>内部资料需有权限的内部账号查看。</p>}
    {!!examples.length && <div className="qa-first-followup"><Suggestions examples={examples} onAsk={onAsk}/></div>}
    {answer.provider && <p className="qa-chat-provider">{external ? 'DeepSeek · 外部参考回答' : answer.provider === '本地证据核对' ? '已逐项核对原文' : '已使用本地模型'}</p>}
  </article>
}

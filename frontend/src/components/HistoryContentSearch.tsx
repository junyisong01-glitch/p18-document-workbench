import { useState, type FormEvent } from 'react'
import { Search } from 'lucide-react'
import { searchLibrary, useSession, type ApiHit } from '@/lib/session'
import { documentTitleParts } from '@/lib/document-title'
import { DocPreviewDialog } from './DocView'
import { SearchEvidence } from './SearchEvidence'

export function HistoryContentSearch() {
  const { visibleDocs } = useSession()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<ApiHit[] | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<ApiHit | null>(null)
  const documents = new Map(visibleDocs.map(doc => [doc.id, doc]))
  const hits = results?.flatMap(hit => {
    const doc = documents.get(hit.document_id)
    return doc ? [{ hit, doc }] : []
  })
  const preview = selected ? documents.get(selected.document_id) ?? null : null

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const term = query.trim()
    if (!term || pending) return
    setResults(null)
    setError('')
    setPending(true)
    try {
      const { body } = await searchLibrary(term, true)
      setResults(body.results)
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setPending(false)
    }
  }

  return <details className="rounded-lg border border-border bg-card px-4 py-3">
    <summary className="w-fit cursor-pointer text-sm font-medium">查正文（含历史）</summary>
    <p className="mt-2 text-xs text-muted-foreground">查找有权阅读的现行和历史版本正文。结果仅供查阅。</p>
    <form className="mt-3 flex gap-2" onSubmit={submit}>
      <input aria-label="查找历史与现行正文" placeholder="输入错误码、接口名或正文关键词"
        className="min-w-0 flex-1 rounded-md border border-border bg-background px-3 py-2 text-sm"
        value={query} maxLength={2000} onChange={event => setQuery(event.target.value)}/>
      <button type="submit" className="dm-primary shrink-0" disabled={pending || !query.trim()}>
        <Search size={14}/> 查正文
      </button>
    </form>
    {pending && <p role="status" className="mt-3 text-sm text-muted-foreground">正在查找正文…</p>}
    {error && <p role="alert" className="mt-3 text-sm text-destructive">{error}</p>}
    {hits?.length === 0 && <p role="status" className="mt-3 text-sm text-muted-foreground">未找到可查阅的正文。</p>}
    {!!hits?.length && <ul className="mt-3 space-y-2">
      {hits.map(({ hit, doc }) => {
        const { title } = documentTitleParts(doc.fileName)
        return <li key={doc.id + '/' + hit.chunk_id} className="space-y-2 rounded-md border border-border bg-background/40 p-3">
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <strong className="text-sm text-foreground">{title}</strong>
            <span>{doc.version}</span>
            <span>{hit.historical ? '历史归档' : '现行版本'}</span>
            {hit.section && <span>{hit.section}</span>}
          </div>
          <SearchEvidence documentId={doc.id} sourceRef={hit}/>
          <button type="button" className="se-source text-xs text-[hsl(12_74%_38%)]" onClick={() => setSelected(hit)}>查看命中证据与原文</button>
        </li>
      })}
    </ul>}
    <DocPreviewDialog doc={preview} sourceRef={selected ?? undefined} open={!!preview} onClose={() => setSelected(null)}/>
  </details>
}

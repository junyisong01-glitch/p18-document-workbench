// 页面四：知识检索（核心页面）
// 自然语言输入 → 混合检索 Top-5 → 结果卡片（排名/片段/来源/格式/版本/相关度）
// → 点击结果查看证据与来源。保留服务端真实排名与融合分数。
import { useEffect, useRef, useState } from 'react'
import { BadgeCheck, CornerDownRight, Loader2, Search } from 'lucide-react'
import { PageHeader, FormatMark, EmptyResult } from '@/components/bits'
import { DocPreviewDialog } from '@/components/DocView'
import { SearchEvidence } from '@/components/SearchEvidence'
import {
  docInKb,
  searchLibrary,
  useKnowledgeBase,
  useSession,
  type SearchOutput,
} from '@/lib/session'
import type { Doc, SearchResult } from '@/lib/types'

const SUGGESTED = [
  '网络重试使同一条设备指令执行两次，对应什么缺陷？',
  'V1.3.1 修复了哪些缺陷？',
  '回归测试的准入结论是什么？',
]

function ResultCard({
  result,
  onOpen,
}: {
  result: SearchResult
  onOpen: (doc: Doc, sourceRef?:SearchResult['sourceRef']) => void
}) {
  const { doc, snippet } = result
  return (
    <article
      data-search-rank={result.rank}
      data-document-id={doc.id}
      className="search-result-card ease-junyi group block w-full border border-border bg-card text-left transition-all duration-200 hover:border-[hsl(12_74%_42%/0.5)]"
    >
      <div className="flex gap-5 px-6 py-5">
        {/* 排名 */}
        <div className="flex w-10 shrink-0 flex-col items-center">
          <span className="font-mono2 text-[26px] font-semibold leading-none tracking-tight text-muted-foreground/70 transition-colors duration-200 group-hover:text-[hsl(12_74%_42%)]">
            {String(result.rank).padStart(2, '0')}
          </span>
          <span className="mt-2 h-px w-6 bg-border" />
          <span className="mt-2 font-mono2 text-[9px] uppercase tracking-[0.14em] text-muted-foreground">
            RANK
          </span>
        </div>

        {/* 主体 */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <FormatMark format={doc.format} className="size-6 [&>svg]:size-3" />
            <button type="button" onClick={() => onOpen(doc,result.sourceRef)} className="se-title text-[14px] font-semibold leading-snug">{doc.fileName}</button>
          </div>

          {/* 证据片段 */}
          <div className="se-evidence mt-3 border-l-2 border-[hsl(12_74%_42%/0.55)]">
            <div className="flex items-center gap-2 font-mono2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              <CornerDownRight className="size-3" />
              命中证据节选 · {snippet.section}
            </div>
            <div className="mt-2"><SearchEvidence documentId={doc.id} sourceRef={result.sourceRef}/></div>
          </div>

          {/* 来源与相关度 */}
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground">
            <span className="font-mono2">{doc.code}</span>{result.historical&&<span className="border border-border px-2">历史版本 · 仅查阅，不用于问答</span>}
            <span>{doc.dept}</span>
            <span className="font-mono2">文档 {doc.version}</span>
            <span>{doc.category}</span>
            {doc.indexStatus === 'review-pending' && (
              <span className="text-[hsl(36_60%_32%)]">索引待复核</span>
            )}
            <button type="button" onClick={() => onOpen(doc,result.sourceRef)} className="se-source text-[hsl(12_74%_38%)]">查看命中证据与原文 →</button>
            <span className="ml-auto flex items-center gap-2" title="融合分数用于当前检索排序，并非答案正确率或百分比">
              <span className="font-mono2 text-[10px] uppercase tracking-[0.12em]">融合分数</span>
              <span className="font-mono2 text-[11px] font-semibold">{result.score.toFixed(4)}</span>
            </span>
          </div>
        </div>
      </div>
    </article>
  )
}

export default function SearchPage() {
  const { searchableDocs, visibleDocs, user, kbId } = useSession()
  const kb = useKnowledgeBase()
  const [includeHistory,setIncludeHistory]=useState(false)
  const [query, setQuery] = useState('')
  const [output, setOutput] = useState<SearchOutput | null>(null)
  const [error, setError] = useState('')
  const [searching, setSearching] = useState(false)
  const [sourceRef,setSourceRef]=useState<SearchResult['sourceRef']>(undefined)
  const [previewing, setPreviewing] = useState<Doc | null>(null)
  const requestId=useRef(0)

  // 切换知识库后清空上一库的检索结果（两库数据隔离，不混合展示）
  useEffect(() => {
    requestId.current+=1
    setOutput(null)
    setIncludeHistory(false)
    setQuery('')
    setError('')
    setSearching(false)
    setPreviewing(null)
  }, [kbId,user?.username])

  const doSearch = async (q: string) => {
    const trimmed = q.trim()
    if (!trimmed || searching) return
    const currentRequest=++requestId.current
    setSearching(true)
    setError('')
    try {
      const { body, elapsedMs } = await searchLibrary(trimmed,includeHistory&&kbId==='business')
      if(currentRequest!==requestId.current)return
      const byId = new Map((includeHistory?visibleDocs:searchableDocs).map((doc) => [doc.id, doc]))
      const results = body.results
        .map((hit) => ({ hit, doc: byId.get(hit.document_id) }))
        // 服务端按权限过滤；这里只再按当前知识库视图筛选
        .filter((row): row is { hit: typeof row.hit; doc: Doc } => !!row.doc && docInKb(row.doc, kbId))
        .map(({ hit, doc }) => ({
          rank: hit.rank,
          historical:hit.historical,
          score: hit.score,
          sourceRef:{revision:hit.revision,index_token:hit.index_token,chunk_id:hit.chunk_id},
          doc,
          snippet: { id: hit.chunk_id, section: hit.section || '文档级', text: hit.text },
        }))
      setOutput({ results, verifiedCase: false, elapsedMs })
    } catch (error) {
      if(currentRequest!==requestId.current)return
      setError(error instanceof Error ? error.message : '检索失败，请稍后重试。')
      setOutput(null)
    } finally {
      if(currentRequest===requestId.current)setSearching(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-6">
      <PageHeader
        kicker="Hybrid Search"
        title="知识检索"
        desc={`${kb.name} · 向量与关键词融合检索，默认返回 Top-5；检索范围按你的岗位权限过滤，${includeHistory?'高级查阅包含有权历史版本，不能加入问答证据':'主搜索仅含当前已发布且索引有效资料'}。`}
      />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-y border-border py-3 text-[12px] text-muted-foreground">
        <span>当前身份：{user?.name} · {user?.role.name}</span>
        <span>可见 {visibleDocs.length} 份 · 可检索 {searchableDocs.length} 份</span>
        <span>结果随岗位权限变化；部门主管不自动获得机密读权，老板检索也只查有效发布版本。</span>
      </div>

      {kbId==='business'&&<label className="flex items-center gap-2 text-sm"><input type="checkbox" aria-label="包含历史版本" checked={includeHistory} onChange={e=>{requestId.current+=1;setSearching(false);setIncludeHistory(e.target.checked);setOutput(null);setPreviewing(null)}}/>高级搜索：包含有权历史版本（独立查阅，不供RAG使用）</label>}
      {/* 检索输入 */}
      <form
        onSubmit={(e) => {
          e.preventDefault()
          doSearch(query)
        }}
        className="flex gap-3"
      >
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-4 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="用自然语言描述你要查的技术问题…"
            aria-label="检索问题"
            className="ease-junyi h-12 w-full rounded-md border border-input bg-card pl-11 pr-4 text-[14px] outline-none transition-colors duration-200 placeholder:text-muted-foreground/60 focus:border-[hsl(12_74%_42%)] focus:ring-2 focus:ring-[hsl(12_74%_42%/0.18)]"
          />
        </div>
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="ease-junyi flex h-12 items-center gap-2 rounded-md bg-[hsl(12_74%_42%)] px-6 text-[14px] font-semibold text-[hsl(44_40%_97%)] transition-colors duration-200 hover:bg-[hsl(12_74%_38%)] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {searching ? <Loader2 className="size-4 animate-spin" /> : <Search className="size-4" />}
          {searching ? '检索中' : '检 索'}
        </button>
      </form>

      {/* 建议问题（含已验证演示案例） */}
      {!output && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12px] text-muted-foreground">试试：</span>
          {SUGGESTED.map((q, i) => (
            <button
              key={q}
              onClick={() => {
                setQuery(q)
                doSearch(q)
              }}
              className={`ease-junyi flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[12px] transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${
                i === 0
                  ? 'border-[hsl(12_74%_42%/0.4)] bg-[hsl(12_74%_42%/0.06)] text-[hsl(12_74%_38%)] hover:bg-[hsl(12_74%_42%/0.1)]'
                  : 'border-border bg-card text-foreground/80 hover:border-muted-foreground/40'
              }`}
            >
              {i === 0 && <BadgeCheck className="size-3.5" />}
              {q}
            </button>
          ))}
        </div>
      )}

      {/* 结果区 */}
      {error && (
        <p role="alert" className="border-l-2 border-[hsl(12_74%_42%)] pl-4 text-[13px] text-[hsl(12_74%_38%)]">
          {error}
        </p>
      )}
      {output && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3 text-[12px] text-muted-foreground">
            <span>
              服务端混合检索 · 返回 Top-{output.results.length} · {output.elapsedMs} ms
            </span>
            <span className="font-mono2 text-[10px] uppercase tracking-[0.14em]">
              {kb.readonly ? 'READ ONLY' : 'MANAGED'}
            </span>
          </div>

          {output.results.length === 0 ? (
            <EmptyResult />
          ) : (
            <div className="grid grid-cols-[minmax(0,1fr)] gap-3">
              {output.results.map((r) => (
                <ResultCard
                  key={`${r.doc.id}-${r.snippet.id}`}
                  result={r}
                  onOpen={(doc,ref)=>{setSourceRef(ref);setPreviewing(doc)}}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <DocPreviewDialog sourceRef={sourceRef} doc={previewing} open={!!previewing} onClose={() => setPreviewing(null)} />
    </div>
  )
}

import { documentTitleParts } from '../lib/document-title'
import BusinessPage from './BusinessPage'
import {DocumentFormat} from '@/components/DocumentLayout'
// 页面三：文档管理（优化版）
// 结构：文件夹卡片 → 文档类型卡片 → 名称搜索 → 文档列表 → 详情抽屉。
// 管理员（现有权限）在可写演示资料库中额外获得上传与内容复核入口；
// 启辰智造 30 份库对任何账号保持只读。上传、复核与状态均使用原生接口。
import { useEffect, useMemo, useState } from 'react'
import {
  Download,
  Eye,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  Folder,
  Lock,
  Search,
  Upload,
  X,
  ClipboardCheck,
} from 'lucide-react'
import { PageHeader, FormatMark, EmptyResult } from '@/components/bits'
import { DocPreviewDialog, PipelineRow } from '@/components/DocView'
import { downloadDemoFile, useKnowledgeBase, useSession } from '@/lib/session'
import type { Doc, DocFormat } from '@/lib/types'
import { UploadDialog, ReviewDialog } from '@/components/DocAdmin'

// ---------------------------------------------------------------------------
// 状态标签（区分有效状态 / 处理状态 / 索引状态，三者可组合共存）
// ---------------------------------------------------------------------------

function ValidityBadge({ doc }: { doc: Doc }) {
  if (doc.status === 'archived') {
    return (
      <span className="inline-flex items-center rounded-sm border border-border bg-secondary px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
        已废止
      </span>
    )
  }
  return (
    <span className="inline-flex items-center rounded-sm border border-[hsl(148_32%_32%/0.45)] bg-[hsl(148_32%_32%/0.08)] px-2 py-0.5 text-[11px] font-medium text-[hsl(148_32%_26%)]">
      现行
    </span>
  )
}

function ReviewBadge({ reviewed, pending }: { reviewed: boolean; pending?:boolean }) {
  if(!reviewed&&!pending)return <span className="text-[11px] text-muted-foreground">无需人工复核</span>
  if (reviewed) {
    return (
      <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span className="size-1.5 rounded-full bg-[hsl(148_32%_32%)]" />
        已复核
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[hsl(36_60%_30%)]">
      <span className="size-1.5 rounded-full bg-[hsl(36_68%_38%)]" />
      待内容复核
    </span>
  )
}

function IndexBadge({doc}:{doc:Doc}) {
  if(!doc.pipeline.indexed)return <span className="text-[11px] text-muted-foreground">{doc.status==='archived'?'已停用检索':doc.processingStatus||'索引未就绪'}</span>
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <span className="size-1.5 rounded-full bg-[hsl(148_32%_32%)]" />
      索引已完成
    </span>
  )
}

// ---------------------------------------------------------------------------
// 文件夹卡片
// ---------------------------------------------------------------------------

function FolderCards({
  docs,
  active,
  onSelect,
}: {
  docs: Doc[]
  active: string
  onSelect: (cat: string) => void
}) {
  const groups = useMemo(() => {
    const map = new Map<string, number>()
    for (const d of docs) map.set(d.category, (map.get(d.category) ?? 0) + 1)
    return [...map.entries()]
  }, [docs])

  const card = (
    id: string,
    name: string,
    sub: string,
    count: number,
    icon: React.ReactNode,
  ) => {
    const isActive = active === id
    return (
      <button
        key={id}
        onClick={() => onSelect(id)}
        className={`ease-junyi group flex items-center gap-3.5 border px-4 py-3.5 text-left transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${
          isActive
            ? 'border-[hsl(12_74%_42%/0.55)] bg-[hsl(12_74%_42%/0.06)]'
            : 'border-border bg-card hover:border-muted-foreground/40'
        }`}
      >
        <span
          className={`flex size-9 items-center justify-center rounded-md border transition-colors duration-200 ${
            isActive
              ? 'border-[hsl(12_74%_42%/0.5)] text-[hsl(12_74%_42%)]'
              : 'border-border text-muted-foreground group-hover:text-foreground'
          }`}
        >
          {icon}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-medium">{name}</span>
          <span className="mt-0.5 block font-mono2 text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
            {sub}
          </span>
        </span>
        <span
          className={`font-mono2 text-[18px] font-semibold ${
            isActive ? 'text-[hsl(12_74%_42%)]' : 'text-foreground/70'
          }`}
        >
          {count}
        </span>
      </button>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {card('__all__', '全部文档', 'All accessible', docs.length, <FolderOpen className="size-4" strokeWidth={1.8} />)}
      {groups.map(([cat, count]) => {
        // 目录编码形如「06_研发部」；无编码前缀的目录（如演示库「平台资料」）原样展示
        const m = /^(\d{2})_(.+)$/.exec(cat)
        return card(
          cat,
          m ? m[2] : cat,
          m ? m[1] : 'Folder',
          count,
          <Folder className="size-4" strokeWidth={1.8} />,
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// 类型卡片（仅展示当前库真实存在的格式；数量按当前账号可见范围统计）
// ---------------------------------------------------------------------------

const TYPE_META: Record<DocFormat, { label: string; en: string; icon: typeof FileText }> = {
  docx: { label: 'Word 文档', en: 'DOCX', icon: FileText },
  xlsx: { label: 'Excel 表格', en: 'XLSX', icon: FileSpreadsheet },
  pdf: { label: 'PDF 文档', en: 'PDF', icon: FileText },
  doc: {label: '旧版 Word', en: 'DOC', icon: FileText},
  xls: {label: '旧版 Excel', en: 'XLS', icon: FileText},
  txt: {label: '纯文本', en: 'TXT', icon: FileText},
  md: {label: 'Markdown 文档', en: 'MD', icon: FileText},
  csv: {label: 'CSV 表格', en: 'CSV', icon: FileText},
  jpg: {label: '图片', en: 'JPG', icon: FileText},
  jpeg: {label: '图片', en: 'JPEG', icon: FileText},
  png: {label: '图片', en: 'PNG', icon: FileText},
}

function TypeCards({
  docs,
  active,
  onSelect,
}: {
  docs: Doc[]
  active: DocFormat | null
  onSelect: (f: DocFormat | null) => void
}) {
  const counts = useMemo(() => {
    const map = new Map<DocFormat, number>()
    for (const d of docs) map.set(d.format, (map.get(d.format) ?? 0) + 1)
    return map
  }, [docs])

  const formats = (Object.keys(TYPE_META) as DocFormat[]).filter((f) => (counts.get(f) ?? 0) > 0)

  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className="kicker shrink-0">类型</span>
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onSelect(null)}
          className={`ease-junyi rounded-md border px-3.5 py-2 text-[12px] transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${
            active === null
              ? 'border-[hsl(12_74%_42%/0.55)] bg-[hsl(12_74%_42%/0.06)] font-medium text-[hsl(12_74%_38%)]'
              : 'border-border bg-card text-foreground/80 hover:border-muted-foreground/40'
          }`}
        >
          全部
        </button>
        {formats.map((f) => {
          const meta = TYPE_META[f]
          const isActive = active === f
          return (
            <button
              key={f}
              onClick={() => onSelect(isActive ? null : f)}
              className={`ease-junyi flex items-center gap-2.5 rounded-md border px-3.5 py-2 transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${
                isActive
                  ? 'border-[hsl(12_74%_42%/0.55)] bg-[hsl(12_74%_42%/0.06)]'
                  : 'border-border bg-card hover:border-muted-foreground/40'
              }`}
            >
              <meta.icon
                className={`size-4 ${isActive ? 'text-[hsl(12_74%_42%)]' : 'text-muted-foreground'}`}
                strokeWidth={1.8}
              />
              <span className={`text-[12px] ${isActive ? 'font-medium text-[hsl(12_74%_38%)]' : 'text-foreground/80'}`}>
                {meta.label}
              </span>
              <span className="font-mono2 text-[11px] text-muted-foreground">
                {counts.get(f)}
              </span>
            </button>
          )
        })}
      </div>
      <span className="ml-auto text-[11px] text-muted-foreground">按当前账号可见范围统计</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 主页面
// ---------------------------------------------------------------------------

function LegacyDocumentsPage() {
  const { visibleDocs, user } = useSession()
  const kb = useKnowledgeBase()
  const [category, setCategory] = useState('__all__')
  const [subcat, setSubcat] = useState<string | null>(null)
  const [format, setFormat] = useState<DocFormat | null>(null)
  const [nameQuery, setNameQuery] = useState('')
  const [selected, setSelected] = useState<Doc | null>(null)
  const [previewing, setPreviewing] = useState<Doc | null>(null)
  const [showUpload, setShowUpload] = useState(false)
  const [reviewing, setReviewing] = useState<Doc | null>(null)

  // 换库时重置筛选
  useEffect(() => {
    setCategory('__all__')
    setSubcat(null)
    setFormat(null)
    setNameQuery('')
    setSelected(null)
  }, [kb.id])

  const docs = visibleDocs

  const subcategories = useMemo(() => {
    if (category !== '06_研发部') return []
    const set = new Set<string>()
    for (const d of docs) if (d.subcategory) set.add(d.subcategory)
    return [...set]
  }, [category, docs])

  const filtered = useMemo(() => {
    const q = nameQuery.trim().toLowerCase()
    return docs.filter((d) => {
      if (category !== '__all__' && d.category !== category) return false
      if (subcat && d.subcategory !== subcat) return false
      if (format && d.format !== format) return false
      if (q && !d.fileName.toLowerCase().includes(q) && !d.code.toLowerCase().includes(q) && !d.title.toLowerCase().includes(q))
        return false
      return true
    })
  }, [docs, category, subcat, format, nameQuery])

  const canManage = !!user?.admin && !kb.readonly && kb.managed

  return (
    <div className="document-manager space-y-6">
      <PageHeader
        kicker="Documents"
        title="文档管理"
        desc={`${kb.name} · ${kb.modeLabel} · ${
          canManage
            ? '你可使用上传、内容复核与索引处理等现有管理功能'
            : '你可浏览授权文档、查看处理状态与原文，并下载有权获取的文件'
        }`}
        extra={
          <div className="flex items-center gap-2">
            {kb.readonly && (
              <span className="flex items-center gap-2 rounded-md border border-border bg-secondary/60 px-3 py-2 text-[12px] text-muted-foreground">
                <Lock className="size-3.5" />
                只读知识库
              </span>
            )}
            {canManage && (
              <button
                onClick={() => setShowUpload(true)}
                className="ease-junyi flex items-center gap-2 rounded-md bg-[hsl(12_74%_42%)] px-4 py-2 text-[13px] font-semibold text-[hsl(44_40%_97%)] transition-colors duration-200 hover:bg-[hsl(12_74%_38%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              >
                <Upload className="size-4" />
                上传文档
              </button>
            )}
          </div>
        }
      />

      {/* 文件夹 */}
      <section>
        <div className="kicker mb-3">文件夹 · 按你可访问的文档计数</div>
        <FolderCards docs={docs} active={category} onSelect={(c) => { setCategory(c); setSubcat(null) }} />
        {subcategories.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[11px] text-muted-foreground">研发部内部分类：</span>
            <button
              onClick={() => setSubcat(null)}
              className={`ease-junyi rounded-full border px-3 py-1 text-[11px] transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${
                subcat === null
                  ? 'border-[hsl(12_74%_42%/0.55)] bg-[hsl(12_74%_42%/0.06)] font-medium text-[hsl(12_74%_38%)]'
                  : 'border-border bg-card text-foreground/75 hover:border-muted-foreground/40'
              }`}
            >
              全部
            </button>
            {subcategories.map((s) => (
              <button
                key={s}
                onClick={() => setSubcat(subcat === s ? null : s)}
                className={`ease-junyi rounded-full border px-3 py-1 text-[11px] transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${
                  subcat === s
                    ? 'border-[hsl(12_74%_42%/0.55)] bg-[hsl(12_74%_42%/0.06)] font-medium text-[hsl(12_74%_38%)]'
                    : 'border-border bg-card text-foreground/75 hover:border-muted-foreground/40'
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* 类型 + 搜索 */}
      <section className="flex flex-wrap items-center gap-4">
        <TypeCards docs={docs} active={format} onSelect={setFormat} />
        <div className="relative ml-auto w-[280px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            value={nameQuery}
            onChange={(e) => setNameQuery(e.target.value)}
            placeholder="按文档名称或编号查找…"
            aria-label="按名称查找文档"
            className="ease-junyi h-9 w-full rounded-md border border-input bg-card pl-9 pr-8 text-[12px] outline-none transition-colors duration-200 placeholder:text-muted-foreground/60 focus:border-[hsl(12_74%_42%)] focus:ring-2 focus:ring-[hsl(12_74%_42%/0.18)]"
          />
          {nameQuery && (
            <button
              onClick={() => setNameQuery('')}
              aria-label="清除查找"
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
            >
              <X className="size-3.5" />
            </button>
          )}
        </div>
      </section>

      {/* 文档列表 */}
      {filtered.length === 0 ? (
        <EmptyResult
          title="没有符合条件的文档"
          hint="调整文件夹、类型或名称查找条件；列表仅包含你有权访问的文档。"
        />
      ) : (
        <div className="dm-document-list">{filtered.map(doc=><article key={doc.id} data-document-id={doc.id} className="dm-document-row dm-legacy-row"><div className="dm-row-main"><DocumentFormat format={doc.format.toUpperCase()} secret={doc.confidentiality==='机密'}/><div className="dm-row-copy"><div className="dm-title-line"><button type="button" onClick={()=>setSelected(doc)} className="dm-document-title" title={doc.fileName}>{documentTitleParts(doc.fileName).title}</button>{doc.version&&<span className="dm-version">{doc.version}</span>}</div><p className="dm-row-meta"><span>{doc.dept}</span><span className={'dm-tag '+(doc.confidentiality==='机密'?'dm-tag-secret':'')}>{doc.confidentiality}</span>{doc.subcategory&&<span>{doc.subcategory}</span>}</p></div></div><div className="dm-row-side"><div className="dm-legacy-statuses"><ValidityBadge doc={doc}/><ReviewBadge reviewed={doc.pipeline.reviewed} pending={doc.reviewRequired}/><IndexBadge doc={doc}/></div><div className="dm-legacy-actions"><button type="button" onClick={()=>setSelected(doc)}>详情</button><button type="button" onClick={()=>setPreviewing(doc)} title="查看原文">查看原文</button><button type="button" onClick={()=>downloadDemoFile(doc)} title="下载原文件">下载</button></div></div></article>)}</div>
      )}
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span>
          共 {filtered.length} 份（你有权访问 {docs.length} 份）
        </span>
        <span>「待内容复核」与「索引已完成」可同时成立：复核提示不影响既有索引</span>
      </div>

      {/* 详情抽屉 */}
      {selected && (
        <DetailDrawer
          doc={docs.find((d) => d.id === selected.id) ?? selected}
          canManage={canManage}
          onClose={() => setSelected(null)}
          onPreview={() => setPreviewing(selected)}
          onReview={() => {
            setReviewing(docs.find((d) => d.id === selected.id) ?? selected)
          }}
        />
      )}

      <DocPreviewDialog doc={previewing} open={!!previewing} onClose={() => setPreviewing(null)} />
      <UploadDialog open={showUpload} onClose={() => setShowUpload(false)} />
      <ReviewDialog doc={reviewing} onClose={() => setReviewing(null)} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// 详情抽屉
// ---------------------------------------------------------------------------

function DetailDrawer({
  doc,
  canManage,
  onClose,
  onPreview,
  onReview,
}: {
  doc: Doc
  canManage: boolean
  onClose: () => void
  onPreview: () => void
  onReview: () => void
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`文档详情：${doc.fileName}`}>
      <div className="absolute inset-0 bg-[hsl(36_16%_9%/0.4)] backdrop-blur-[1px]" onClick={onClose} />
      <aside className="scrollbar-thin absolute inset-y-0 right-0 flex w-[440px] flex-col overflow-y-auto border-l border-border bg-card shadow-2xl">
        <div className="flex items-start gap-4 border-b border-border px-6 py-5">
          <FormatMark format={doc.format} className="mt-1" />
          <div className="min-w-0 flex-1">
            <div className="font-mono2 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              {doc.code}
            </div>
            <h3 className="mt-1.5 break-words font-display text-[15px] font-semibold leading-snug">
              {documentTitleParts(doc.fileName).title}
            </h3>
          </div>
          <button
            onClick={onClose}
            aria-label="关闭详情"
            className="ease-junyi rounded-md p-2 text-muted-foreground transition-colors duration-200 hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="flex-1 space-y-6 px-6 py-5">
          {/* 基本信息 */}
          <section>
            <div className="kicker mb-3">基本信息</div>
            <dl className="space-y-2.5">
              {[
                ['所属部门', doc.dept],
                ['所属文件夹', doc.category],
                ...(doc.subcategory ? [['内部分类', doc.subcategory] as [string, string]] : []),
                ['文档版本', doc.version],
                ['文件类型', doc.format.toUpperCase()],
                ['密级', doc.confidentiality],
              ].map(([k, v]) => (
                <div key={k} className="grid grid-cols-[88px_minmax(0,1fr)] items-baseline gap-3">
                  <dt className="font-mono2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                    {k}
                  </dt>
                  <dd className="text-[13px]">{v}</dd>
                </div>
              ))}
            </dl>
          </section>

          {/* 处理状态 */}
          <section>
            <div className="kicker mb-3">处理与索引</div>
            <div className="space-y-3 border border-border bg-secondary/30 px-4 py-4">
              <PipelineRow doc={doc} />
              <div className="flex items-center justify-between border-t border-border/70 pt-3">
                <span className="text-[11px] text-muted-foreground">复核情况</span>
                <ReviewBadge reviewed={doc.pipeline.reviewed} pending={doc.reviewRequired} />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-muted-foreground">索引状态</span>
                <IndexBadge doc={doc}/>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[11px] text-muted-foreground">有效状态</span>
                <ValidityBadge doc={doc} />
              </div>
              {doc.reviewRequired && !doc.pipeline.reviewed && (
                <p className="border-t border-dashed border-border pt-3 text-[11px] leading-relaxed text-[hsl(36_60%_30%)]">
                  该文档的{doc.format === 'xlsx' ? '结构化解析' : '解析'}结果存在复核提示；索引状态见上方，复核完成后按现有流程处理。
                </p>
              )}
            </div>
          </section>

          {/* 来源 */}
          <section>
            <div className="kicker mb-3">来源与原文</div>
            <div className="space-y-2">
              {doc.snippets.slice(0, 2).map((s) => (
                <div key={s.id} className="border-l-2 border-border pl-3">
                  <div className="font-mono2 text-[10px] text-muted-foreground">{s.section}</div>
                  <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-foreground/80">
                    {s.text}
                  </p>
                </div>
              ))}
            </div>
          </section>
        </div>

        {/* 底部操作 */}
        <div className="space-y-2 border-t border-border px-6 py-4">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={onPreview}
              className="ease-junyi flex flex-1 items-center justify-center gap-2 rounded-md bg-[hsl(12_74%_42%)] px-4 py-2.5 text-[12px] font-semibold text-[hsl(44_40%_97%)] transition-colors duration-200 hover:bg-[hsl(12_74%_38%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
            >
              <Eye className="size-3.5" />
              查看原文
            </button>
            <button
              onClick={() => downloadDemoFile(doc)}
              className="ease-junyi flex flex-1 items-center justify-center gap-2 rounded-md border border-border px-4 py-2.5 text-[12px] font-medium transition-colors duration-200 hover:border-[hsl(12_74%_42%/0.5)] hover:text-[hsl(12_74%_42%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
            >
              <Download className="size-3.5" />
              下载原文件
            </button>
          </div>
          {canManage && doc.reviewRequired && !doc.pipeline.reviewed && (
            <button
              onClick={onReview}
              className="ease-junyi flex w-full items-center justify-center gap-2 rounded-md border border-[hsl(36_68%_38%/0.5)] bg-[hsl(36_68%_38%/0.07)] px-4 py-2.5 text-[12px] font-medium text-[hsl(36_60%_30%)] transition-colors duration-200 hover:bg-[hsl(36_68%_38%/0.12)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(36_68%_38%)]"
            >
              <ClipboardCheck className="size-3.5" />
              进入内容复核（管理操作）
            </button>
          )}
          <p className="text-center font-mono2 text-[9px] uppercase tracking-[0.18em] text-muted-foreground/70">
            下载与预览沿用现有能力 · 演示环境
          </p>
        </div>
      </aside>
    </div>
  )
}

export default function DocumentsPage(){const {kbId}=useSession();return kbId==='business'?<BusinessPage/>:<LegacyDocumentsPage/>}

// 共享小组件：状态徽章、文件类型标记、演示环境标签、空状态等。
import { FileSpreadsheet, FileText, SearchX } from 'lucide-react'
import type { Doc, DocFormat } from '@/lib/types'

/** 运行环境统一标注：已连接后端，数据来自服务端 */
export function DemoTag({ className = '' }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border border-dashed border-[hsl(36_68%_38%/0.55)] bg-[hsl(36_68%_38%/0.08)] px-2.5 py-1 font-mono2 text-[10px] font-medium uppercase tracking-[0.14em] text-[hsl(36_60%_32%)] ${className}`}
    >
      <span className="size-1.5 rounded-full bg-[hsl(36_68%_38%)]" />
      已连接后端 · 实时数据
    </span>
  )
}

/** 文档格式标记（等宽编号风格，不用彩色图标容器） */
export function FormatMark({ format, className = '' }: { format: DocFormat; className?: string }) {
  const Icon = ['xlsx','xls','csv'].includes(format) ? FileSpreadsheet : FileText
  return (
    <span
      className={`inline-flex size-8 items-center justify-center rounded-md border border-border bg-card text-muted-foreground ${className}`}
    >
      <Icon className="size-4" strokeWidth={1.8} />
    </span>
  )
}

/** 文档状态徽章 */
export function StatusBadge({ doc }: { doc: Doc }) {
  if (doc.status === 'archived') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-sm border border-border bg-secondary px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
        已废止 · 仅归档查看
      </span>
    )
  }
  if (doc.indexStatus === 'review-pending') {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-sm border border-[hsl(36_68%_38%/0.5)] bg-[hsl(36_68%_38%/0.08)] px-2 py-0.5 text-[11px] font-medium text-[hsl(36_60%_30%)]">
        <span className="size-1.5 rounded-full bg-[hsl(36_68%_38%)]" />
        索引待复核
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-sm border border-[hsl(148_32%_32%/0.45)] bg-[hsl(148_32%_32%/0.08)] px-2 py-0.5 text-[11px] font-medium text-[hsl(148_32%_26%)]">
      <span className="size-1.5 rounded-full bg-[hsl(148_32%_32%)]" />
      现行 · 可检索
    </span>
  )
}

/** 空检索结果 */
export function EmptyResult({
  title = '未检索到相关文档',
  hint = '换个关键词试试；检索范围限定在你有权限的现行文档内。',
}: {
  title?: string
  hint?: string
}) {
  return (
    <div className="flex flex-col items-center gap-3 border border-dashed border-border px-6 py-16 text-center">
      <SearchX className="size-8 text-muted-foreground/60" strokeWidth={1.5} />
      <div className="text-sm font-medium">{title}</div>
      <div className="max-w-sm text-xs leading-relaxed text-muted-foreground">{hint}</div>
    </div>
  )
}

/** 页面标题区 */
export function PageHeader({
  kicker,
  title,
  desc,
  extra,
}: {
  kicker: string
  title: string
  desc?: string
  extra?: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
      <div>
        <div className="kicker">{kicker}</div>
        <h1 className="mt-2 font-display text-[26px] font-semibold leading-tight tracking-tight">
          {title}
        </h1>
        {desc && (
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted-foreground">
            {desc}
          </p>
        )}
      </div>
      {extra}
    </div>
  )
}

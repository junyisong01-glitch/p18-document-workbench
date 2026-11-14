import { CheckCircle2, AlertTriangle } from 'lucide-react';
import type { Classification, DocStatus } from '@/types/document';

const CLASSIFICATION_STYLES: Record<Classification, string> = {
  未分类: 'bg-slate-100 text-slate-600',
  公开: 'bg-slate-100 text-slate-600',
  内部: 'bg-blue-50 text-blue-700',
  机密: 'bg-red-50 text-red-600',
};

const STATUS_STYLES: Record<DocStatus, string> = {
  可检索: 'bg-emerald-50 text-emerald-700',
  已停用检索: 'bg-slate-100 text-slate-500',
  待分类: 'bg-slate-100 text-slate-600',
  待复核: 'bg-amber-50 text-amber-700',
  待建索引: 'bg-slate-100 text-slate-600',
  处理失败: 'bg-red-50 text-red-600',
  处理中: 'bg-amber-50 text-amber-700',
};

const PILL = 'inline-flex items-center whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium';

export function ClassificationBadge({ value }: { value: Classification }) {
  return <span className={`${PILL} ${CLASSIFICATION_STYLES[value]}`}>{value}</span>;
}

export function StatusBadge({ value }: { value: DocStatus }) {
  return <span className={`${PILL} ${STATUS_STYLES[value]}`}>{value}</span>;
}

export function QcBadge({ issues, reviewed = false }: { issues: string[]; reviewed?: boolean }) {
  if (reviewed) return <span className={`${PILL} gap-1 bg-emerald-50 text-emerald-700`}><CheckCircle2 className="h-3.5 w-3.5" />已复核{issues.length > 0 ? ` · 保留${issues.length}项原提示` : ''}</span>;
  if (issues.length === 0) {
    return (
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-ink-muted">
        <CheckCircle2 className="h-4 w-4 text-emerald-500" strokeWidth={2} />
        未发现解析异常
      </span>
    );
  }
  return (
    <span className={`${PILL} gap-1 bg-amber-50 text-amber-700`}>
      <AlertTriangle className="h-3.5 w-3.5" strokeWidth={2} />
      需要复核 · {issues.length} 项
    </span>
  );
}

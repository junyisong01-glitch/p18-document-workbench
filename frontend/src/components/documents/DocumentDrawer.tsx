import { AlertTriangle, CheckCircle2, X } from 'lucide-react';
import { useEffect, type ReactNode } from 'react';
import type { DocumentRecord } from '@/types/document';
import ExcelPreview from './ExcelPreview';
import { ClassificationBadge, QcBadge, StatusBadge } from '@/components/documents/DocumentBadges';

interface DocumentDrawerProps {
  doc: DocumentRecord;
  onClose: () => void;
  onEdit?: () => void;
}

const PASSED_CHECKS = ['当前未记录解析异常；不代表内容事实已经核验。'];

function InfoItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-ink-subtle">{label}</dt>
      <dd className="mt-1.5 text-sm font-medium text-ink">{children}</dd>
    </div>
  );
}

export default function DocumentDrawer({ doc, onClose, onEdit }: DocumentDrawerProps) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 animate-fade-in bg-[#18233A]/30" onClick={onClose} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="文档详情"
        className={`absolute bottom-0 right-0 top-0 flex w-full ${doc.format === 'XLSX' ? 'max-w-[1100px]' : 'max-w-[480px]'} animate-drawer-in flex-col bg-white shadow-dialog`}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line-soft px-6 py-5">
          <div className="min-w-0">
            <p className="text-xs font-medium text-blue-600">文档详情</p>
            <h2 className="mt-1.5 text-lg font-semibold leading-[1.3] text-ink">{doc.name}</h2>
            <p className="mt-1 text-sm text-ink-muted">
              {doc.code} · {doc.format}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="-mr-1 rounded-lg p-1.5 text-ink-subtle transition hover:bg-slate-100 hover:text-ink"
          >
            <X className="h-5 w-5" strokeWidth={1.75} />
          </button>
        </div>

        <div className="flex-1 space-y-8 overflow-y-auto px-6 py-6">
          <section>
            <h3 className="text-sm font-semibold text-ink">基本信息</h3>
            <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-5 rounded-xl border border-line-soft bg-slate-50/50 p-5">
              <InfoItem label="所在文件夹">{doc.folder}</InfoItem>
              <InfoItem label="所属部门">{doc.department}</InfoItem>
              <InfoItem label="文档类型">{doc.docType}</InfoItem>
              <InfoItem label="密级">
                <ClassificationBadge value={doc.classification} />
              </InfoItem>
              <InfoItem label="处理状态">
                <StatusBadge value={doc.status} />
              </InfoItem>
              <InfoItem label="版本号">{doc.version}</InfoItem>
              <InfoItem label="有效状态">{doc.lifecycle}</InfoItem>
              <InfoItem label="文档编号">{doc.code}</InfoItem>
              <InfoItem label="文件格式">{doc.format}</InfoItem>
            </dl>
          </section>

          <section>
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-ink">质量检查</h3>
              <QcBadge issues={doc.qcIssues} reviewed={doc.reviewCompleted && doc.status !== '待复核'} />
            </div>
            {doc.reviewCompleted && doc.status !== '待复核' && doc.qcIssues.length > 0 && <p className="mt-3 text-sm text-ink-muted">当前版本已完成复核；以下为保留的原检查提示，并非新的待办。</p>}
            <ul className="mt-4 space-y-2.5">
              {doc.qcIssues.map((issue) => (
                <li key={issue} className="flex gap-3 rounded-xl border border-amber-200 bg-amber-50/60 p-3.5 text-sm leading-[1.5] text-amber-800">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.75} />
                  {issue}
                </li>
              ))}
              {doc.qcIssues.length === 0 &&
                PASSED_CHECKS.map((check) => (
                  <li key={check} className="flex items-center gap-3 text-sm text-ink-muted">
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" strokeWidth={2} />
                    {check}
                  </li>
                ))}
            </ul>
          </section>

          {doc.format === 'XLSX' ? <ExcelPreview identifier={doc.id} reviewSearchable={doc.reviewSearchable}/> : (
          <section>
            <h3 className="text-sm font-semibold text-ink">文字预览</h3>
            <div className="mt-4 rounded-xl border border-line-soft bg-white p-5 whitespace-pre-wrap text-sm leading-[1.8] text-ink-muted shadow-inner">
              {doc.preview || '暂未提取正文，请核对处理状态。'}
            </div>
          </section>)}

        </div>

        <div className="flex flex-wrap gap-3 justify-end border-t border-line-soft bg-slate-50/60 px-6 py-4">
          <a className="py-2 text-blue-600" href={`/api/documents/${encodeURIComponent(doc.id)}/file/original`}>下载原文件</a>
          <a className="py-2 text-blue-600" href={`/?document=${encodeURIComponent(doc.id)}`}>解析、切分与复核</a>
          {onEdit&&<button onClick={onEdit} className="py-2 text-blue-600">编辑分类与权限</button>}
          <button
            type="button"
            onClick={onClose}
            className="h-10 rounded-xl border border-line bg-white px-5 text-sm font-medium text-ink transition hover:bg-slate-50"
          >
            关闭
          </button>
        </div>
      </aside>
    </div>
  );
}

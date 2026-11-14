import { Eye, Trash2 } from 'lucide-react';
import type { DocumentRecord } from '@/types/document';
import { ClassificationBadge, QcBadge, StatusBadge } from '@/components/documents/DocumentBadges';
import Pagination from '@/components/documents/Pagination';

interface DocumentTableProps {
  manager: boolean;
  rows: DocumentRecord[];
  total: number;
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
  onView: (doc: DocumentRecord) => void;
  onDelete: (doc: DocumentRecord) => void;
  onClearFilters: () => void;
}

const HEADERS = ['文档名称', '所属部门', '类型', '密级', '版本 / 生效', '处理状态', '质量检查', '操作'];

export default function DocumentTable({
  manager,
  rows,
  total,
  page,
  pageCount,
  onPageChange,
  onView,
  onDelete,
  onClearFilters,
}: DocumentTableProps) {
  return (
    <div className="flex flex-col">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] border-collapse text-left">
          <thead>
            <tr className="border-b border-line bg-slate-50/70">
              {HEADERS.map((header) => (
                <th key={header} className="whitespace-nowrap px-4 py-3 text-xs font-medium text-ink-subtle">
                  {header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((doc) => {
              const retired = doc.status === '已停用检索';
              return (
                <tr key={doc.id} className="border-b border-line-soft transition-colors last:border-b-0 hover:bg-blue-50/50">
                  <td className="min-w-[220px] px-4 py-4 align-middle">
                    <p className={`text-sm font-semibold leading-[1.5] ${retired ? 'text-ink-muted' : 'text-ink'}`}>
                      {doc.name}
                    </p>
                    <p className="mt-0.5 text-xs leading-[1.5] text-ink-subtle">
                      {doc.code} · {doc.format}
                    </p>
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 align-middle text-sm text-ink-muted">{doc.department}</td>
                  <td className="whitespace-nowrap px-4 py-4 align-middle text-sm text-ink-muted">{doc.docType}</td>
                  <td className="px-4 py-4 align-middle">
                    <ClassificationBadge value={doc.classification} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 align-middle">
                    <p className="text-sm font-medium text-ink">{doc.version}</p>
                    {doc.effectiveDate === '已废止' ? (
                      <span className="mt-1 inline-flex rounded-md bg-red-50 px-2 py-0.5 text-xs font-medium text-red-600">
                        已废止
                      </span>
                    ) : (
                      <p className="mt-0.5 text-xs leading-[1.5] text-ink-subtle">{doc.effectiveDate}</p>
                    )}
                  </td>
                  <td className="px-4 py-4 align-middle">
                    <StatusBadge value={doc.status} />
                  </td>
                  <td className="px-4 py-4 align-middle">
                    <QcBadge issues={doc.qcIssues} reviewed={doc.reviewCompleted && doc.status !== '待复核'} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 align-middle">
                    <div className="flex items-center gap-4 text-sm">
                      <button
                        type="button"
                        onClick={() => onView(doc)}
                        className="inline-flex items-center gap-1 font-medium text-blue-600 transition hover:text-blue-800"
                      >
                        <Eye className="h-3.5 w-3.5" strokeWidth={1.75} />
                        查看
                      </button>
                      {manager && <button
                        type="button"
                        onClick={() => onDelete(doc)}
                        className="inline-flex items-center gap-1 font-medium text-ink-muted transition hover:text-red-600"
                      >
                        <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} />
                        删除
                      </button>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && (
          <div className="flex flex-col items-center gap-3 px-6 py-16 text-center">
            <p className="text-sm font-medium text-ink">没有符合条件的文档</p>
            <p className="text-sm text-ink-muted">可以调整筛选条件，或联系管理员核对资料范围。</p>
            <button
              type="button"
              onClick={onClearFilters}
              className="mt-1 rounded-lg px-3 py-1.5 text-sm font-medium text-blue-600 transition hover:bg-blue-50"
            >
              清除筛选
            </button>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4 border-t border-line-soft px-5 py-4">
        <p className="text-xs leading-[1.5] text-ink-muted">
          共 {total} 份文档。灰色"已停用检索"的文档仅留档，不会作为回答来源。
        </p>
        {pageCount > 1 && <Pagination page={page} pageCount={pageCount} onPageChange={onPageChange} />}
      </div>
    </div>
  );
}

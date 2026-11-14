import { FolderPlus, Plus } from 'lucide-react';

interface PageHeaderProps {
  manager: boolean;
  onCreateFolder: () => void;
  onUpload: () => void;
}

export default function PageHeader({ manager, onCreateFolder, onUpload }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-6 py-2">
      <div>
        <h1 className="text-[28px] font-semibold leading-[1.2] tracking-tight text-ink">文档资料库</h1>
        <p className="mt-2 text-sm leading-[1.5] text-ink-muted">
          仅展示当前身份可见的资料。文件夹按主题归档，部门、类型和有效状态可单独筛选。
        </p>
      </div>
      {manager && <div className="flex shrink-0 items-center gap-3">
        <button
          type="button"
          onClick={onCreateFolder}
          className="inline-flex h-12 items-center gap-2 rounded-xl border border-line bg-white px-4 text-sm font-medium text-ink shadow-sm transition hover:border-blue-200 hover:bg-blue-50/50 hover:text-blue-700 active:scale-[0.98]"
        >
          <FolderPlus className="h-4 w-4" strokeWidth={1.75} />
          新建文件夹
        </button>
        <button
          type="button"
          onClick={onUpload}
          className="inline-flex h-12 items-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-medium text-white shadow-[0_6px_16px_rgba(37,99,235,0.25)] transition hover:bg-blue-700 active:scale-[0.98]"
        >
          <Plus className="h-4 w-4" strokeWidth={2} />
          上传文档
        </button>
      </div>}
    </div>
  );
}

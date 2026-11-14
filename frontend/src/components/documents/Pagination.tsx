import { ChevronLeft, ChevronRight } from 'lucide-react';

interface PaginationProps {
  page: number;
  pageCount: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, pageCount, onPageChange }: PaginationProps) {
  const buttonBase =
    'inline-flex h-8 min-w-[32px] items-center justify-center rounded-lg px-2 text-sm tabular-nums transition disabled:cursor-not-allowed disabled:opacity-40';

  return (
    <nav aria-label="分页" className="flex items-center gap-1.5">
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        aria-label="上一页"
        className={`${buttonBase} text-ink-muted hover:bg-slate-100 hover:text-ink`}
      >
        <ChevronLeft className="h-4 w-4" strokeWidth={1.75} />
      </button>
      {Array.from({ length: pageCount }, (_, index) => index + 1).map((item) => (
        <button
          key={item}
          type="button"
          onClick={() => onPageChange(item)}
          aria-current={item === page ? 'page' : undefined}
          className={`${buttonBase} ${
            item === page ? 'bg-blue-600 font-medium text-white shadow-sm' : 'text-ink-muted hover:bg-slate-100 hover:text-ink'
          }`}
        >
          {item}
        </button>
      ))}
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= pageCount}
        aria-label="下一页"
        className={`${buttonBase} text-ink-muted hover:bg-slate-100 hover:text-ink`}
      >
        <ChevronRight className="h-4 w-4" strokeWidth={1.75} />
      </button>
    </nav>
  );
}

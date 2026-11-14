import { X } from 'lucide-react';
import { useEffect, type ReactNode } from 'react';

interface ModalProps {
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer: ReactNode;
  widthClass?: string;
  spacious?: boolean;
}

export default function Modal({
  title,
  description,
  onClose,
  children,
  footer,
  widthClass = 'max-w-[600px]',
  spacious = false,
}: ModalProps) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6">
      <div className="absolute inset-0 animate-fade-in bg-[#18233A]/35 backdrop-blur-[2px]" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`relative flex max-h-[calc(100vh-48px)] w-full ${widthClass} animate-dialog-in flex-col overflow-hidden rounded-2xl border border-line bg-white shadow-dialog`}
      >
        <div className={`flex items-start justify-between gap-4 border-b border-line-soft ${spacious ? 'px-6 py-6 sm:px-8' : 'px-6 py-5'}`}>
          <div>
            <h2 className={`${spacious ? 'text-2xl' : 'text-lg'} font-semibold leading-[1.2] text-ink`}>{title}</h2>
            {description && <p className="mt-1 text-sm leading-[1.5] text-ink-muted">{description}</p>}
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
        <div className={`min-h-0 overflow-y-auto ${spacious ? 'px-6 py-7 sm:px-8' : 'px-6 py-5'}`}>{children}</div>
        <div className={`flex shrink-0 justify-end gap-3 border-t border-line-soft bg-slate-50/60 ${spacious ? 'px-6 py-5 sm:px-8' : 'px-6 py-4'}`}>{footer}</div>
      </div>
    </div>
  );
}

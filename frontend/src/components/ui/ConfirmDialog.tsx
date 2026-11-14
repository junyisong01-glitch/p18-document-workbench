import { useState } from 'react';
import Modal from '@/components/ui/Modal';

interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}

export default function ConfirmDialog({ title, message, confirmLabel, onConfirm, onClose }: ConfirmDialogProps) {
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  const handleConfirm = async () => {
    setPending(true);
    setErrorMessage('');
    try {
      await onConfirm();
      onClose();
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '操作失败，请稍后重试');
      setPending(false);
    }
  };

  return (
    <Modal
      title={title}
      onClose={onClose}
      widthClass="max-w-[440px]"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            disabled={pending}
            className="h-10 rounded-xl border border-line bg-white px-5 text-sm font-medium text-ink transition hover:bg-slate-50 disabled:opacity-50"
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={pending}
            className="h-10 rounded-xl bg-red-600 px-5 text-sm font-medium text-white shadow-[0_6px_16px_rgba(220,38,38,0.2)] transition hover:bg-red-700 disabled:opacity-60"
          >
            {pending ? '删除中…' : confirmLabel}
          </button>
        </>
      }
    >
      <p className="text-sm leading-[1.7] text-ink-muted">{message}</p>
      {errorMessage && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{errorMessage}</p>}
    </Modal>
  );
}

import { useState } from 'react';
import FormField from '@/components/ui/FormField';
import Modal from '@/components/ui/Modal';
import { INPUT_CLASS } from '@/components/ui/formStyles';

interface NewDocTypeDialogProps {
  existingNames: string[];
  onSubmit: (name: string) => Promise<void>;
  onClose: () => void;
}

export default function NewDocTypeDialog({ existingNames, onSubmit, onClose }: NewDocTypeDialogProps) {
  const [name, setName] = useState('');
  const [nameError, setNameError] = useState('');
  const [pending, setPending] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const handleSubmit = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setNameError('请填写类型名称');
      return;
    }
    if (existingNames.includes(trimmed)) {
      setNameError('已存在同名类型');
      return;
    }

    setPending(true);
    setSubmitError('');
    try {
      await onSubmit(trimmed);
      onClose();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : '创建失败，请稍后重试');
      setPending(false);
    }
  };

  return (
    <Modal
      title="新建文档类型"
      description="新类型会出现在左侧“按类型”列表和上传表单的类型选项中。"
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
            onClick={handleSubmit}
            disabled={pending}
            className="h-10 rounded-xl bg-blue-600 px-5 text-sm font-medium text-white shadow-[0_6px_16px_rgba(37,99,235,0.25)] transition hover:bg-blue-700 active:scale-[0.98] disabled:opacity-60"
          >
            {pending ? '创建中…' : '创建类型'}
          </button>
        </>
      }
    >
      <FormField label="类型名称" required error={nameError || submitError}>
        <input
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setNameError('');
            setSubmitError('');
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') void handleSubmit();
          }}
          maxLength={12}
          autoFocus
          placeholder="如 会议纪要"
          className={INPUT_CLASS}
        />
      </FormField>
    </Modal>
  );
}

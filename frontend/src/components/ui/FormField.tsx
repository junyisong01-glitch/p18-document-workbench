import type { ReactNode } from 'react';

interface FormFieldProps {
  label: string;
  required?: boolean;
  error?: string;
  hint?: string;
  children: ReactNode;
}

export default function FormField({ label, required, error, hint, children }: FormFieldProps) {
  return (
    <div className="flex flex-col">
      <span className="mb-1.5 text-sm font-medium text-ink">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </span>
      {children}
      {error ? (
        <p className="mt-1.5 text-xs text-red-600">{error}</p>
      ) : hint ? (
        <p className="mt-1.5 text-xs leading-[1.5] text-ink-subtle">{hint}</p>
      ) : null}
    </div>
  );
}

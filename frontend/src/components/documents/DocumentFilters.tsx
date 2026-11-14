import { AlertTriangle, ChevronDown, Search } from 'lucide-react';
import type { ReactNode } from 'react';
import { CLASSIFICATIONS, type Classification } from '@/types/document';

export interface DocumentFilterValues {
  keyword: string;
  department: string;
  docType: string;
  classification: '' | Classification;
  reviewOnly: boolean;
  lifecycle: string;
}

interface DocumentFiltersProps {
  values: DocumentFilterValues;
  docTypeOptions: string[];
  departmentOptions: string[];
  onChange: (next: Partial<DocumentFilterValues>) => void;
}

function FilterSelect({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="relative">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 cursor-pointer appearance-none rounded-xl border border-line bg-white py-0 pl-3.5 pr-9 text-sm text-ink transition hover:border-blue-200 focus:border-blue-400 focus:outline-none focus:ring-4 focus:ring-blue-100"
      >
        {children}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" strokeWidth={1.75} />
    </label>
  );
}

export default function DocumentFilters({ values, departmentOptions, docTypeOptions, onChange }: DocumentFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="flex h-10 min-w-[220px] flex-1 items-center gap-2.5 rounded-xl border border-line bg-slate-50/70 px-3.5 transition focus-within:border-blue-400 focus-within:bg-white focus-within:ring-4 focus-within:ring-blue-100">
        <Search className="h-4 w-4 shrink-0 text-ink-subtle" strokeWidth={1.75} />
        <input
          value={values.keyword}
          onChange={(event) => onChange({ keyword: event.target.value })}
          placeholder="搜索文档名称或编号…"
          className="w-full bg-transparent text-sm text-ink placeholder:text-ink-subtle focus:outline-none"
        />
      </label>

      <FilterSelect label="所属部门" value={values.department} onChange={(department) => onChange({ department })}>
        <option value="">全部部门</option>
        {departmentOptions.map((name) => (
          <option key={name} value={name}>
            {name}
          </option>
        ))}
      </FilterSelect>

      <FilterSelect
        label="文档类型"
        value={values.docType}
        onChange={(docType) => onChange({ docType })}
      >
        <option value="">全部类型</option>
        {docTypeOptions.map((type) => (
          <option key={type} value={type}>
            {type}
          </option>
        ))}
      </FilterSelect>

      <FilterSelect
        label="密级"
        value={values.classification}
        onChange={(classification) => onChange({ classification: classification as '' | Classification })}
      >
        <option value="">全部密级</option>
        {CLASSIFICATIONS.map((level) => (
          <option key={level} value={level}>
            {level}
          </option>
        ))}
      </FilterSelect>

      <FilterSelect label="有效状态" value={values.lifecycle} onChange={lifecycle=>onChange({lifecycle})}>
        <option value="">全部状态</option><option>现行有效</option><option>已废止</option>
      </FilterSelect>
      <button
        type="button"
        aria-pressed={values.reviewOnly}
        onClick={() => onChange({ reviewOnly: !values.reviewOnly })}
        className={`inline-flex h-10 items-center gap-2 rounded-xl border px-3.5 text-sm font-medium transition active:scale-[0.98] ${
          values.reviewOnly
            ? 'border-amber-300 bg-amber-50 text-amber-700'
            : 'border-line bg-white text-ink-muted hover:border-amber-200 hover:text-amber-700'
        }`}
      >
        <AlertTriangle className="h-4 w-4" strokeWidth={1.75} />
        仅看需要复核
      </button>
    </div>
  );
}

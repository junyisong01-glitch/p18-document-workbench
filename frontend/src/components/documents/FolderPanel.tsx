import { Lock, Plus } from 'lucide-react';
import type { ReactNode } from 'react';
import { ARCHIVE_FOLDER, type Classification, type LibraryScope } from '@/types/document';

export interface FolderItem {
  name: string;
  count: number;
  accessible: boolean;
  custom: boolean;
}

export interface CountItem<T extends string> {
  value: T;
  count: number;
}

interface FolderPanelProps {
  manager: boolean;
  scope: LibraryScope;
  onScopeChange: (scope: LibraryScope) => void;
  folders: FolderItem[];
  docTypes: CountItem<string>[];
  classifications: CountItem<Classification>[];
  totalCount: number;
  onCreateDocType: () => void;
}

const FOLDER_COLORS: Record<string, string> = {
  公司公共制度: 'bg-blue-500',
  行政安全部: 'bg-cyan-500',
  生产制造部: 'bg-orange-400',
  人力资源部: 'bg-violet-500',
  财务部: 'bg-emerald-500',
  研发部: 'bg-sky-400',
  [ARCHIVE_FOLDER]: 'bg-slate-400',
};
const CUSTOM_FOLDER_COLOR = 'bg-teal-500';

const CLASSIFICATION_DOT: Record<Classification, string> = {
  未分类: 'bg-slate-400',
  公开: 'bg-slate-400',
  内部: 'bg-blue-500',
  机密: 'bg-red-500',
};

function isSameScope(a: LibraryScope, b: LibraryScope): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === 'all') return true;
  if (a.kind === 'folder' && b.kind === 'folder') return a.name === b.name;
  if (a.kind === 'docType' && b.kind === 'docType') return a.value === b.value;
  if (a.kind === 'classification' && b.kind === 'classification') return a.value === b.value;
  return false;
}

function ItemButton({
  active,
  disabled,
  onClick,
  children,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2 text-sm transition ${
        active
          ? 'bg-blue-50 font-medium text-blue-700'
          : disabled
            ? 'cursor-not-allowed text-ink-subtle'
            : 'text-ink hover:bg-slate-50'
      }`}
    >
      {children}
    </button>
  );
}

function SectionTitle({ children }: { children: ReactNode }) {
  return <h3 className="px-3 text-xs font-semibold tracking-wide text-ink-subtle">{children}</h3>;
}

export default function FolderPanel({
  scope,
  onScopeChange,
  folders,
  docTypes,
  classifications,
  totalCount,
  manager,
  onCreateDocType,
}: FolderPanelProps) {
  const allScope: LibraryScope = { kind: 'all' };

  return (
    <div className="sticky top-6 flex flex-col gap-1 p-5">
      <SectionTitle>文件夹</SectionTitle>
      <div className="mt-2 flex flex-col gap-0.5">
        <ItemButton active={isSameScope(scope, allScope)} onClick={() => onScopeChange(allScope)}>
          <span className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-blue-600" />
            全部文档
          </span>
          <span className="text-xs tabular-nums text-ink-muted">{totalCount}</span>
        </ItemButton>
        {folders.map((folder) => {
          const active = isSameScope(scope, { kind: 'folder', name: folder.name });
          const colorClass = folder.custom
            ? CUSTOM_FOLDER_COLOR
            : (FOLDER_COLORS[folder.name] ?? CUSTOM_FOLDER_COLOR);
          return (
            <ItemButton
              key={folder.name}
              active={active}
              disabled={!folder.accessible}
              onClick={() => onScopeChange({ kind: 'folder', name: folder.name })}
            >
              <span className="flex min-w-0 items-center gap-2.5">
                <span
                  className={`h-2.5 w-2.5 shrink-0 rounded-sm ${folder.accessible ? colorClass : 'bg-slate-300'}`}
                />
                <span className="truncate">{folder.name}</span>
              </span>
              {folder.accessible ? (
                <span className="text-xs tabular-nums text-ink-muted">{folder.count}</span>
              ) : (
                <span className="flex shrink-0 items-center gap-1 rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-ink-subtle">
                  <Lock className="h-3 w-3" strokeWidth={2} />
                  无权限
                </span>
              )}
            </ItemButton>
          );
        })}
      </div>

      <div className="my-5 h-px bg-line-soft" />

      <div className="flex items-center justify-between pr-1">
        <SectionTitle>按类型</SectionTitle>
        <button
          type="button"
          disabled={!manager} onClick={onCreateDocType}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium text-blue-600 transition hover:bg-blue-50 hover:text-blue-800"
        >
          <Plus className="h-3.5 w-3.5" strokeWidth={2} />
          新建
        </button>
      </div>
      <div className="mt-2 flex flex-col gap-0.5">
        {docTypes.map((item) => (
          <ItemButton
            key={item.value}
            active={isSameScope(scope, { kind: 'docType', value: item.value })}
            onClick={() => onScopeChange({ kind: 'docType', value: item.value })}
          >
            <span>{item.value}</span>
            <span className="text-xs tabular-nums text-ink-muted">{item.count}</span>
          </ItemButton>
        ))}
      </div>

      <div className="my-5 h-px bg-line-soft" />

      <SectionTitle>按密级</SectionTitle>
      <div className="mt-2 flex flex-col gap-0.5">
        {classifications.map((item) => (
          <ItemButton
            key={item.value}
            active={isSameScope(scope, { kind: 'classification', value: item.value })}
            onClick={() => onScopeChange({ kind: 'classification', value: item.value })}
          >
            <span className="flex items-center gap-2.5">
              <span className={`h-2 w-2 rounded-full ${CLASSIFICATION_DOT[item.value]}`} />
              {item.value}
            </span>
            <span className="text-xs tabular-nums text-ink-muted">{item.count}</span>
          </ItemButton>
        ))}
      </div>
    </div>
  );
}

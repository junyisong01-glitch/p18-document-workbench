import { useMemo, useState } from 'react';
import ConfirmDialog from '@/components/ui/ConfirmDialog';
import Sidebar from '@/components/layout/Sidebar';
import TopBar from '@/components/layout/TopBar';
import DocumentDrawer from '@/components/documents/DocumentDrawer';
import DocumentFilters, { type DocumentFilterValues } from '@/components/documents/DocumentFilters';
import DocumentTable from '@/components/documents/DocumentTable';
import FolderPanel, { type CountItem, type FolderItem } from '@/components/documents/FolderPanel';
import NewFolderDialog from '@/components/documents/NewFolderDialog';
import NewDocTypeDialog from '@/components/documents/NewDocTypeDialog';
import PageHeader from '@/components/documents/PageHeader';
import StatCards, { type LibraryStats } from '@/components/documents/StatCards';
import UploadDialog from '@/components/documents/UploadDialog';
import { api } from '@/lib/documentStore';
import { useDocumentLibrary } from '@/hooks/useDocumentLibrary';
import {
  ARCHIVE_FOLDER,
  CLASSIFICATIONS,
  DEPARTMENTS,
  type Classification,
  type DocumentRecord,
  type FolderRecord,
  type IdentityKey,
  type LibraryScope,
} from '@/types/document';

const PAGE_SIZE = 10;
const ALL_SCOPE: LibraryScope = { kind: 'all' };
const BASE_FOLDER_NAMES: string[] = [];

const INITIAL_FILTERS: DocumentFilterValues = {
  keyword: '',
  department: '',
  docType: '',
  classification: '',
  reviewOnly: false,
  lifecycle: '',
};

type DialogState =
  | { kind: 'upload' }
  | { kind: 'edit'; doc: DocumentRecord }
  | { kind: 'folder' }
  | { kind: 'docType' }
  | { kind: 'view'; id: string }
  | { kind: 'delete'; doc: DocumentRecord }
  | null;

function scopeTitle(scope: LibraryScope): string {
  switch (scope.kind) {
    case 'all':
      return '全部文档';
    case 'folder':
      return scope.name;
    case 'docType':
      return scope.value;
    case 'classification':
      return `${scope.value}文档`;
  }
}

function matchesScope(doc: DocumentRecord, scope: LibraryScope): boolean {
  switch (scope.kind) {
    case 'all':
      return true;
    case 'folder':
      return doc.folder === scope.name;
    case 'docType':
      return doc.docType === scope.value;
    case 'classification':
      return doc.classification === scope.value;
  }
}

function matchesFilters(doc: DocumentRecord, filters: DocumentFilterValues): boolean {
  if (filters.lifecycle && doc.lifecycle !== filters.lifecycle) return false;
  if (filters.department && doc.department !== filters.department) return false;
  if (filters.docType && doc.docType !== filters.docType) return false;
  if (filters.classification && doc.classification !== filters.classification) return false;
  if (filters.reviewOnly && !(doc.status === '待复核' || (!doc.reviewCompleted && doc.qcIssues.length > 0))) return false;
  const keyword = filters.keyword.trim().toLowerCase();
  if (keyword && !doc.name.toLowerCase().includes(keyword) && !doc.code.toLowerCase().includes(keyword)) {
    return false;
  }
  return true;
}

export default function DocumentsPage() {
  const { documents, folders, docTypes, user, loadState, errorMessage, reload, addDocument, removeDocument, addFolder, addDocType } =
    useDocumentLibrary();
  const [scope, setScope] = useState<LibraryScope>(ALL_SCOPE);
  const [filters, setFilters] = useState<DocumentFilterValues>(INITIAL_FILTERS);
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState<DialogState>(null);

  const visibleDocs = useMemo(
    () => documents,
    [documents],
  );

  const folderItems: FolderItem[] = useMemo(() => {
    const toItem = (name: string, custom: boolean, folder?: FolderRecord): FolderItem => ({
      name,
      custom,
      count: visibleDocs.filter((doc) => doc.folder === name).length,
      accessible: true,
    });
    return [
      ...BASE_FOLDER_NAMES.map((name) => toItem(name, false)),
      ...folders.map((folder) => toItem(folder.name, true, folder)),
    ];
  }, [documents, folders, visibleDocs]);

  const activeScope: LibraryScope =
    scope.kind === 'folder' && !folderItems.some((item) => item.name === scope.name && item.accessible)
      ? ALL_SCOPE
      : scope;

  const countBy = <T extends string>(values: T[], options: readonly T[]): CountItem<T>[] =>
    options.map((value) => ({ value, count: values.filter((item) => item === value).length }));

  const docTypeNames = docTypes.map((type) => type.name);
  const docTypeCounts = countBy(
    visibleDocs.map((doc) => doc.docType),
    docTypeNames,
  );
  const classificationCounts = countBy<Classification>(
    visibleDocs.map((doc) => doc.classification),
    CLASSIFICATIONS,
  );

  const stats: LibraryStats = {
    viewable: visibleDocs.length,
    processing: visibleDocs.filter((doc) => doc.status === '处理中').length,
    needsReview: visibleDocs.filter((doc) => doc.status === '待复核' || (!doc.reviewCompleted && doc.qcIssues.length > 0)).length,
    searchable: visibleDocs.filter((doc) => doc.status === '可检索').length,
    confidential: visibleDocs.filter((doc) => doc.classification === '机密').length,
  };

  const filteredDocs = useMemo(
    () =>
      visibleDocs.filter((doc) => matchesScope(doc, activeScope) && matchesFilters(doc, filters)),
    [visibleDocs, activeScope, filters],
  );

  const pageCount = Math.max(1, Math.ceil(filteredDocs.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageRows = filteredDocs.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const viewedDoc = dialog?.kind === 'view' ? documents.find((doc) => doc.id === dialog.id) : undefined;
  const departmentOptions = [...DEPARTMENTS];

  const changeScope = (next: LibraryScope) => {
    setScope(next);
    setPage(1);
  };

  const changeFilters = (next: Partial<DocumentFilterValues>) => {
    setFilters((prev) => ({ ...prev, ...next }));
    setPage(1);
  };


  const clearFilters = () => {
    setFilters(INITIAL_FILTERS);
    setScope(ALL_SCOPE);
    setPage(1);
  };

  return (
    <div className="flex min-h-screen bg-gradient-to-b from-[#F3F8FF] to-[#E8F0FB]">
      <Sidebar />

      <main className="flex min-w-0 flex-1 flex-col gap-6 px-6 py-6">
        <TopBar
          demo={user.demo}
          identity={user.identity}
          onSearchSubmit={(keyword) => changeFilters({ keyword })}
        />

        <PageHeader manager={user.manager || user.demo} onCreateFolder={() => setDialog({ kind: 'folder' })} onUpload={() => setDialog({ kind: 'upload' })} />

        <StatCards stats={stats} />

        {errorMessage && (
          <div className="flex items-center justify-between gap-4 rounded-2xl border border-red-200 bg-red-50 px-5 py-3 text-sm text-red-700">
            <span>{errorMessage}</span>
            <button
              type="button"
              onClick={() => void reload()}
              className="shrink-0 rounded-lg px-3 py-1.5 font-medium text-red-700 transition hover:bg-red-100"
            >
              重新加载
            </button>
          </div>
        )}

        <section className="flex min-h-[600px] overflow-hidden rounded-2xl border border-line bg-white shadow-card">
          <aside className="w-[232px] shrink-0 border-r border-line-soft">
            <FolderPanel
              scope={activeScope}
              onScopeChange={changeScope}
              folders={folderItems}
              docTypes={docTypeCounts}
              classifications={classificationCounts}
              totalCount={visibleDocs.length}
              manager={user.manager}
              onCreateDocType={() => setDialog({ kind: 'docType' })}
            />
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <div className="flex flex-col gap-4 border-b border-line-soft px-6 py-5">
              <div className="flex items-baseline gap-3">
                <h2 className="text-lg font-semibold leading-[1.2] text-ink">{scopeTitle(activeScope)}</h2>
                <span className="text-sm text-ink-subtle">{filteredDocs.length} 份</span>
              </div>
              <DocumentFilters
                values={filters}
                departmentOptions={departmentOptions}
                docTypeOptions={docTypeNames}
                onChange={changeFilters}
              />
            </div>

            {loadState === 'loading' ? (
              <div className="flex flex-1 items-center justify-center py-24 text-sm text-ink-muted">正在加载资料…</div>
            ) : (
              <DocumentTable manager={user.manager}
                rows={pageRows}
                total={filteredDocs.length}
                page={currentPage}
                pageCount={pageCount}
                onPageChange={setPage}
                onView={(doc) => setDialog({ kind: 'view', id: doc.id })}
                onDelete={(doc) => setDialog({ kind: 'delete', doc })}
                onClearFilters={clearFilters}
              />
            )}
          </div>
        </section>
      </main>

      {dialog?.kind === 'upload' && (
        <UploadDialog
          folders={folders}
          docTypes={docTypes}
          onSubmit={addDocument}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === 'folder' && (
        <NewFolderDialog
          existingNames={folders.map(f=>f.name)}
          onSubmit={addFolder}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === 'docType' && (
        <NewDocTypeDialog
          existingNames={docTypeNames}
          onSubmit={addDocType}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === 'edit' && <UploadDialog initial={dialog.doc} folders={folders} docTypes={docTypes} onSubmit={addDocument} onSave={async metadata=>{await api(`/api/library/documents/${encodeURIComponent(dialog.doc.id)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...metadata,expected_version:dialog.doc.metadataVersion})});await reload();}} onClose={()=>setDialog(null)}/>}
      {viewedDoc && <DocumentDrawer doc={viewedDoc} onEdit={user.manager?()=>setDialog({kind:'edit',doc:viewedDoc}):undefined} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'delete' && (
        <ConfirmDialog
          title="删除文档"
          message={`确定删除「${dialog.doc.name}」吗？删除后该文档及其处理结果将从资料库删除，请确认。`}
          confirmLabel="确认删除"
          onConfirm={() => removeDocument(dialog.doc.id)}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}

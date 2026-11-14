import {useRef, useState} from 'react';
import {CloudUpload, FileCheck2, ChevronDown} from 'lucide-react';
import Modal from '@/components/ui/Modal';
import {INPUT_CLASS, SELECT_CLASS} from '@/components/ui/formStyles';
import {CLASSIFICATIONS, IDENTITIES, DEPARTMENTS, type DocumentRecord, type FolderRecord, type DocTypeRecord} from '@/types/document';
import type {NewDocumentInput} from '@/lib/documentStore';

export default function UploadDialog({folders, docTypes, onSubmit, onClose, initial, onSave}: {
 initial?: DocumentRecord; onSave?: (metadata: Record<string, unknown>) => Promise<void>;
 folders: FolderRecord[]; docTypes: DocTypeRecord[]; onSubmit: (v: NewDocumentInput) => Promise<void>; onClose: () => void;
}) {
 const inputRef = useRef<HTMLInputElement>(null);
 const [file, setFile] = useState<File|null>(null), [error, setError] = useState(''), [pending, setPending] = useState(false);
 const [dragging, setDragging] = useState(false);
 const [values, setValues] = useState(initial ? {
  name: initial.name, code: initial.code, folder: initial.folder, department: initial.department,
  doc_type: initial.docType, classification: initial.classification === '未分类' ? '内部' : initial.classification,
  version: initial.version, lifecycle: initial.lifecycle,
 } : {name: '', code: '', folder: '', department: '', doc_type: '', classification: '内部', version: 'V1.0', lifecycle: '现行有效'});
 const [viewers, setViewers] = useState<string[]>(initial?.viewers || []);
 const select = (f?: File) => {
  if (!f) return;
  if (!/\.(pdf|docx|doc|xlsx)$/i.test(f.name)) {setError('当前支持 PDF、DOCX、DOC、XLSX。'); return;}
  setFile(f); setValues(v => ({...v, name: f.name.replace(/\.[^.]+$/, '')})); setError('');
 };
 const submit = async () => {
  if ((!initial && !file) || Object.values(values).some(v => !v.trim())) {setError('请选择文件，并填写所有带 * 的必填项。'); return;}
  if (values.classification === '机密' && !viewers.length) {setError('请选择机密文档的可查看人员。'); return;}
  setPending(true);
  try {
   const metadata = {...values, viewers: values.classification === '机密' ? viewers : []};
   if (initial && onSave) await onSave(metadata);
   else if (file) await onSubmit({file, metadata});
   onClose();
  } catch (e) {setError((e as Error).message);} finally {setPending(false);}
 };
 const fieldClass = `${INPUT_CLASS} h-12 px-4`;
 const labelClass = 'block text-sm font-semibold text-ink';
 const required = <span className="ml-1 text-red-500">*</span>;
 const textField = (key: 'name'|'code'|'version', label: string, placeholder: string) => <label className={labelClass}>{label}{required}<input required disabled={pending} className={`${fieldClass} mt-2 font-normal`} placeholder={placeholder} value={values[key]} onChange={e => setValues({...values, [key]: e.target.value})}/></label>;
 const selectField = (key: 'department'|'doc_type'|'folder'|'lifecycle', label: string, options: readonly string[], placeholder: string) => <label className={labelClass}>{label}{required}<span className="relative mt-2 block"><select required disabled={pending} className={`${SELECT_CLASS} h-12 px-4 pr-10 font-normal`} value={values[key]} onChange={e => setValues({...values, [key]: e.target.value})}><option value="">{placeholder}</option>{options.map(v => <option key={v}>{v}</option>)}</select><ChevronDown aria-hidden="true" className="pointer-events-none absolute right-4 top-4 h-4 w-4 text-ink-subtle"/></span></label>;
 return <Modal title={initial ? '编辑分类与权限' : '上传文档'} description={initial ? '保存后权限立即生效；若移除自己的查看权限，该文档将从列表消失。' : '上传后文档会进入处理队列，完成解析和索引后即可检索；需要复核的内容会保留提醒。'} onClose={() => {if (!pending) onClose();}} spacious widthClass="max-w-[880px]" footer={<>
  <button disabled={pending} className="rounded-xl border border-line bg-white px-6 py-3 text-sm font-semibold text-ink transition hover:bg-slate-50 focus-visible:outline-blue-500 disabled:opacity-50" onClick={onClose}>取消</button>
  <button disabled={pending} className="rounded-xl bg-blue-600 px-7 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 focus-visible:outline-blue-500 disabled:opacity-50" onClick={submit}>{pending ? '正在保存…' : initial ? '保存修改' : '确认上传'}</button>
 </>}><fieldset disabled={pending} className="space-y-6 disabled:opacity-60">
  {!initial && <div>
   <p className={labelClass}>选择文件{required}</p>
   <input ref={inputRef} className="sr-only" tabIndex={-1} aria-label="选择文件" type="file" accept=".pdf,.docx,.doc,.xlsx" onChange={e => select(e.target.files?.[0])}/>
   <button type="button" onClick={() => inputRef.current?.click()} onDragOver={e => {e.preventDefault(); setDragging(true);}} onDragLeave={() => setDragging(false)} onDrop={e => {e.preventDefault(); setDragging(false); select(e.dataTransfer.files[0]);}} className={`mt-3 flex min-h-[180px] w-full flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-7 text-center transition focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-100 ${dragging ? 'border-blue-500 bg-blue-50' : 'border-line bg-slate-50/60 hover:border-blue-400 hover:bg-blue-50/50'}`}>
    {file ? <FileCheck2 aria-hidden="true" className="h-10 w-10 text-blue-500" strokeWidth={1.6}/> : <CloudUpload aria-hidden="true" className="h-10 w-10 text-blue-500" strokeWidth={1.6}/>}
    <span className="max-w-full break-all text-base font-semibold text-ink">{file ? file.name : '点击选择或将文件拖拽到此处'}</span>
    <span className="text-sm text-ink-subtle">{file ? '已选择文件，点击可重新选择' : 'PDF、DOCX、DOC、XLSX'}</span>
   </button>
   <p className="mt-2 text-xs leading-5 text-ink-subtle">支持 PDF、DOCX、DOC、XLSX；每次上传一份文件。</p>
  </div>}
  {textField('name', '文档名称', '默认使用文件名，可修改')}
  <div className="grid gap-5 sm:grid-cols-2">
   {selectField('department', '所属部门', DEPARTMENTS, '请选择部门')}
   {selectField('doc_type', '文档类型', docTypes.map(t => t.name), '请选择类型')}
  </div>
  <fieldset><legend className={labelClass}>密级{required}</legend><div className="mt-3 grid grid-cols-3 gap-3">{CLASSIFICATIONS.map(level => <label key={level} className={`flex cursor-pointer items-center gap-3 rounded-xl border px-4 py-3.5 text-sm font-medium transition hover:border-blue-400 ${values.classification === level ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-line text-ink-muted'}`}><input type="radio" name="document-classification" value={level} checked={values.classification === level} onChange={() => setValues({...values, classification: level})} className="h-4 w-4 accent-blue-600"/>{level}</label>)}</div></fieldset>
  {values.classification === '机密' && <fieldset className="rounded-xl border border-amber-200 bg-amber-50/50 p-4"><legend className="px-1 text-sm font-semibold text-ink">可查看人员{required}</legend><p className="text-xs text-ink-muted">机密资料不外发，请明确选择可查看的身份。</p><div className="mt-3 grid gap-3 sm:grid-cols-2">{IDENTITIES.map(i => <label key={i.key} className="flex items-center gap-2 text-sm text-ink"><input type="checkbox" checked={viewers.includes(i.label)} onChange={e => setViewers(e.target.checked ? [...viewers, i.label] : viewers.filter(v => v !== i.label))} className="h-4 w-4 accent-blue-600"/>{i.label}</label>)}</div></fieldset>}
  <div className="grid gap-5 sm:grid-cols-3">
   {textField('code', '文档编号', '请输入文档编号')}
   {textField('version', '版本号', '如 V1.0')}
   {selectField('lifecycle', '有效状态', ['现行有效', '已废止'], '请选择状态')}
  </div>
  {selectField('folder', '所在文件夹', folders.map(f => f.name), '请选择文件夹')}
  {error && <p className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-600" role="alert">{error}</p>}
 </fieldset></Modal>;
}

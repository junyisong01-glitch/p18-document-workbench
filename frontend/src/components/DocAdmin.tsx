// 管理操作组件：上传弹窗与内容复核弹窗。
// 仅对「现有文档管理员 + 可写知识库（演示资料库）」开放；
// 两个弹窗调用原生上传、复核接口，状态由服务端返回。
import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle2, CloudUpload, FileText, X } from 'lucide-react'
import { DemoTag, FormatMark } from './bits'
import { api, uploadDocument } from '@/lib/api'
import { useSession } from '@/lib/session'
import { KNOWLEDGE_BASES, type Doc } from '@/lib/types'

// 现有部门选项（不自动创建新部门）
const DEPTS = ['研发部', '财务部', '人力资源部', '行政安全部', '生产制造部']
// 现有密级分类
const CONFIDENTIALITY = ['公开', '内部', '机密'] as const
// 现有后端支持的上传格式
const ACCEPT = '.doc,.docx,.xlsx,.xls,.pdf,.txt,.md,.csv,.jpg,.jpeg,.png'

interface UploadForm {
  file: File | null
  name: string
  dept: string
  docType: string
  confidentiality: (typeof CONFIDENTIALITY)[number]
  code: string
  version: string
  folder: string
}

const INITIAL: UploadForm = {
  file: null,
  name: '',
  dept: '研发部',
  docType: 'Word（DOCX）',
  confidentiality: '内部',
  code: '',
  version: 'V1.0',
  folder: '',
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string
  required?: boolean
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <label className="mb-1.5 flex items-baseline gap-1.5 text-[12px] font-medium">
        {label}
        {required ? (
          <span className="text-[hsl(12_74%_42%)]">*</span>
        ) : (
          <span className="font-mono2 text-[9px] uppercase tracking-wide text-muted-foreground">
            可选
          </span>
        )}
        {hint && <span className="ml-auto text-[10px] font-normal text-muted-foreground">{hint}</span>}
      </label>
      {children}
    </div>
  )
}

const inputCls =
  'ease-junyi h-10 w-full rounded-md border border-input bg-card px-3 text-[13px] outline-none transition-colors duration-200 placeholder:text-muted-foreground/60 focus:border-[hsl(12_74%_42%)] focus:ring-2 focus:ring-[hsl(12_74%_42%/0.18)]'

export function UploadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { kbId, user, refresh } = useSession()
  const [busy, setBusy] = useState(false)
  const [resultId, setResultId] = useState('')
  const [form, setForm] = useState<UploadForm>(INITIAL)
  const [errors, setErrors] = useState<string[]>([])
  const [submitted, setSubmitted] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  // 文件夹选项使用后端已支持字段：演示资料库现有目录
  const folders = useMemo(() => ['平台资料'], [])
  useEffect(() => {
    if (open) {
      setForm({ ...INITIAL, folder: folders[0] })
      setErrors([])
      setSubmitted(false)
    }
  }, [open, folders])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const set = <K extends keyof UploadForm>(k: K, v: UploadForm[K]) =>
    setForm((f) => ({ ...f, [k]: v }))

  const pickFile = (file: File | null) => {
    if (!file) return
    const ext = file.name.toLowerCase().split('.').pop()
    if (!['doc', 'docx', 'xlsx', 'xls', 'pdf', 'txt', 'md', 'csv', 'jpg', 'jpeg', 'png'].includes(ext||'')) {
      setErrors(['现有上传能力支持 PDF / Word / Excel / TXT / Markdown / CSV / JPG / PNG 格式，请重新选择文件。'])
      return
    }
    setErrors([])
    setForm((f) => ({
      ...f,
      file,
      name: f.name || file.name.replace(/\.(docx?|pdf|xlsx?|txt|md|csv|jpe?g|png)$/i, ''),
      docType: (ext || '').toUpperCase(),
    }))
  }

  const submit = async () => {
    const errs: string[] = []
    if (!form.file) errs.push('请选择要上传的文件')
    if (!form.name.trim()) errs.push('请填写文档名称')
    if (!form.version.trim()) errs.push('请填写文档版本')
    setErrors(errs)
    if (errs.length) return
    setBusy(true)
    try {
      const uploaded = await uploadDocument(form.file as File, {
        expected_version: 0,
        code: form.code.trim(),
        name: form.name.trim(),
        folder: form.folder,
        department: form.dept,
        doc_type: form.docType,
        classification: form.confidentiality,
        version: form.version.trim(),
        lifecycle: '现行有效',
        viewers: form.confidentiality === '机密' && user ? [user.username] : [],
      })
      setResultId(uploaded?.id || '')
      setSubmitted(true)
      await refresh()
    } catch (error) {
      setErrors([error instanceof Error ? error.message : '上传失败，请稍后重试。'])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[hsl(36_16%_9%/0.55)] p-6 backdrop-blur-[2px]"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="上传文档"
    >
      <div
        className="flex max-h-[88vh] w-full max-w-xl flex-col border border-border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <div className="kicker">Upload</div>
            <h3 className="mt-1 font-display text-[16px] font-semibold">上传文档</h3>
            <p className="mt-1 text-[11px] text-muted-foreground">
              目标知识库：{KNOWLEDGE_BASES[kbId].name}（可写 · 管理操作）
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="关闭上传窗口"
            className="ease-junyi rounded-md p-2 text-muted-foreground transition-colors duration-200 hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="scrollbar-thin flex-1 space-y-5 overflow-y-auto px-6 py-5">
          {submitted ? (
            <div className="space-y-4">
              <div className="flex items-start gap-3 border border-[hsl(36_68%_38%/0.5)] bg-[hsl(36_68%_38%/0.07)] px-4 py-4">
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-[hsl(36_60%_32%)]" />
                <div className="text-[13px] leading-relaxed">
                  <p className="font-semibold">上传已提交</p>
                  <p className="mt-1 text-muted-foreground">
                    {resultId ? `文档已写入知识库（${resultId.slice(0, 8)}…）` : '文档已写入知识库'}
                    ，随后进入「解析 → 切分 → 复核 → 索引」流水线；有解析风险时会在列表中标记为待复核。
                  </p>
                </div>
              </div>
              <dl className="space-y-2 border border-border bg-secondary/30 px-4 py-4 text-[12px]">
                {[
                  ['文件', form.file?.name ?? ''],
                  ['文档名称', form.name],
                  ['所属部门', form.dept],
                  ['文档类型', form.docType],
                  ['密级', form.confidentiality],
                  ['文档编号', form.code || '（未填写）'],
                  ['版本', form.version],
                  ['所属文件夹', form.folder],
                ].map(([k, v]) => (
                  <div key={k} className="grid grid-cols-[88px_minmax(0,1fr)] gap-3">
                    <dt className="font-mono2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                      {k}
                    </dt>
                    <dd className="break-all">{v}</dd>
                  </div>
                ))}
              </dl>
              <button
                onClick={onClose}
                className="ease-junyi w-full rounded-md border border-border px-4 py-2.5 text-[12px] font-medium transition-colors duration-200 hover:border-[hsl(12_74%_42%/0.5)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
              >
                完成
              </button>
            </div>
          ) : (
            <>
              {/* 文件选择（拖放仅为现有文件选择的前端操作方式） */}
              <Field label="选择文件" required hint="支持 PDF / Word / Excel / TXT / Markdown / CSV / JPG / PNG">
                <div
                  onDragOver={(e) => {
                    e.preventDefault()
                    setDragOver(true)
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => {
                    e.preventDefault()
                    setDragOver(false)
                    pickFile(e.dataTransfer.files?.[0] ?? null)
                  }}
                  onClick={() => fileRef.current?.click()}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      fileRef.current?.click()
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  className={`ease-junyi flex cursor-pointer flex-col items-center gap-2.5 rounded-md border border-dashed px-4 py-7 text-center transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${
                    dragOver
                      ? 'border-[hsl(12_74%_42%)] bg-[hsl(12_74%_42%/0.06)]'
                      : form.file
                        ? 'border-[hsl(148_32%_32%/0.5)] bg-[hsl(148_32%_32%/0.05)]'
                        : 'border-input bg-secondary/30 hover:border-muted-foreground/50'
                  }`}
                >
                  {form.file ? (
                    <>
                      <FileText className="size-6 text-[hsl(148_32%_32%)]" strokeWidth={1.6} />
                      <span className="break-all text-[12px] font-medium">{form.file.name}</span>
                      <span className="font-mono2 text-[10px] text-muted-foreground">
                        {(form.file.size / 1024).toFixed(1)} KB · 点击可重新选择
                      </span>
                    </>
                  ) : (
                    <>
                      <CloudUpload className="size-6 text-muted-foreground" strokeWidth={1.6} />
                      <span className="text-[12px] text-foreground/80">
                        拖放文件到这里，或点击选择
                      </span>
                      <span className="font-mono2 text-[10px] text-muted-foreground">
                        格式与大小以后端现有规则为准
                      </span>
                    </>
                  )}
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  accept={ACCEPT}
                  className="hidden"
                  onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
                />
              </Field>

              <Field label="文档名称" required hint="默认取文件名，可按现有规则修改">
                <input
                  value={form.name}
                  onChange={(e) => set('name', e.target.value)}
                  placeholder="例如：设备监控平台接口说明"
                  className={inputCls}
                />
              </Field>

              <div className="grid grid-cols-2 gap-4">
                <Field label="所属部门" required>
                  <select
                    value={form.dept}
                    onChange={(e) => set('dept', e.target.value)}
                    className={inputCls}
                  >
                    {DEPTS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="文档类型" required>
                  <select
                    value={form.docType}
                    onChange={(e) => set('docType', e.target.value)}
                    className={inputCls}
                  >
                    <option>Word（DOCX）</option><option>DOC</option><option>DOCX</option><option>XLSX</option><option>XLS</option><option>PDF</option><option>TXT</option><option>MD</option><option>CSV</option><option>JPG</option><option>JPEG</option><option>PNG</option>
                    <option>Excel（XLSX）</option>
                  </select>
                </Field>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Field label="密级" required hint="用于文档分级，访问规则仍由后端控制">
                  <div className="flex gap-2">
                    {CONFIDENTIALITY.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => set('confidentiality', c)}
                        className={`ease-junyi flex-1 rounded-md border px-3 py-2 text-[12px] transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${
                          form.confidentiality === c
                            ? 'border-[hsl(12_74%_42%/0.55)] bg-[hsl(12_74%_42%/0.06)] font-medium text-[hsl(12_74%_38%)]'
                            : 'border-border bg-card text-foreground/75 hover:border-muted-foreground/40'
                        }`}
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                </Field>
                <Field label="所属文件夹" required hint="使用现有文件夹，不可新建">
                  <select
                    value={form.folder}
                    onChange={(e) => set('folder', e.target.value)}
                    className={inputCls}
                  >
                    {folders.map((f) => (
                      <option key={f} value={f}>
                        {f}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Field label="文档编号（选填）" hint="有公司编号时填写">
                  <input
                    value={form.code}
                    onChange={(e) => set('code', e.target.value)}
                    placeholder="例如：QC-RD-API-002"
                    className={`${inputCls} font-mono2`}
                  />
                </Field>
                <Field label="文档版本" required>
                  <input
                    value={form.version}
                    onChange={(e) => set('version', e.target.value)}
                    placeholder="例如：V1.0"
                    className={`${inputCls} font-mono2`}
                  />
                </Field>
              </div>

              {errors.length > 0 && (
                <div
                  role="alert"
                  className="space-y-1 rounded-md border border-[hsl(4_72%_40%/0.4)] bg-[hsl(4_72%_40%/0.06)] px-3.5 py-2.5"
                >
                  {errors.map((e) => (
                    <p key={e} className="text-[12px] text-[hsl(4_72%_36%)]">
                      {e}
                    </p>
                  ))}
                </div>
              )}

              <DemoTag />
            </>
          )}
        </div>

        {!submitted && (
          <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-4">
            <button
              onClick={onClose}
              className="ease-junyi rounded-md border border-border px-4 py-2 text-[12px] text-muted-foreground transition-colors duration-200 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
            >
              取消
            </button>
            <button
              onClick={submit}
              disabled={busy}
              className="ease-junyi rounded-md bg-[hsl(12_74%_42%)] px-5 py-2 text-[12px] font-semibold text-[hsl(44_40%_97%)] transition-colors duration-200 hover:bg-[hsl(12_74%_38%)] disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
            >
              {busy ? '正在上传…' : '上传文档'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// 内容复核弹窗：核对解析正文 / 表格与来源信息，按现有规则完成复核。
// ---------------------------------------------------------------------------

export function ReviewDialog({ doc, onClose }: { doc: Doc | null; onClose: () => void }) {
  const { markReviewed, refresh, user } = useSession()
  const [done, setDone] = useState(false)
  const [detail, setDetail] = useState<{
    revision: number
    pending: boolean
    issues: string[]
    blocks: Array<{id:string;label?:string;text:string}>
    requirements: Array<{ key: string; label: string }>
  } | null>(null)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [error, setError] = useState('')

  useEffect(() => {
    setDone(false); setError(''); setDetail(null); setChecked({})
    if (!doc) return
    let alive = true
    api.get<{
      revision: number
      review_pending?: boolean
      review_requirements?: Array<{ key: string; label: string }>
      result?: { blocks?: Array<{id:string;label?:string;text:string}>; issues?: Array<{ message?: string }> }
    }>(
      `/api/documents/${doc.id}`,
    ).then((body) => {
      if (!alive) return
      setDetail({
        revision: body.revision,
        pending: !!body.review_pending,
        issues: (body.result?.issues || []).map((i) => i.message || '解析风险').slice(0, 6),
        blocks: body.result?.blocks || [],
        requirements: (body.review_requirements || []).map((r) => ({ key: r.key, label: r.label })),
      })
    }).catch((e) => alive && setError(e instanceof Error ? e.message : '无法读取文档状态'))
    return () => { alive = false }
  }, [doc])

  useEffect(() => {
    if (!doc) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [doc, onClose])

  if (!doc) return null

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-[hsl(36_16%_9%/0.55)] p-6 backdrop-blur-[2px]"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`内容复核：${doc.fileName}`}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col border border-border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-4 border-b border-border px-6 py-4">
          <FormatMark format={doc.format} className="mt-0.5" />
          <div className="min-w-0 flex-1">
            <div className="kicker">Content Review</div>
            <h3 className="mt-1 break-words font-display text-[15px] font-semibold leading-snug">
              {doc.fileName}
            </h3>
            <p className="mt-1 text-[11px] text-muted-foreground">
              核对解析{doc.format === 'xlsx' ? '表格' : '正文'}与来源信息，确认后按现有规则完成复核
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="关闭复核窗口"
            className="ease-junyi rounded-md p-2 text-muted-foreground transition-colors duration-200 hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
          >
            <X className="size-4" />
          </button>
        </div>

        <div className="scrollbar-thin flex-1 space-y-4 overflow-y-auto px-6 py-5">
          <DemoTag />
          {!detail&&!error&&<p>正在读取真实解析内容…</p>}
          {detail?.blocks.map(block=><section key={block.id}>
            <b className="text-xs">{block.label||block.id}</b>
            <pre className="whitespace-pre-wrap border-l pl-4 text-sm">{block.text}</pre>
          </section>)}
          {detail&&!detail.blocks.length&&<p role="alert">没有可核对的解析正文，请下载原件并检查处理状态。</p>}
          {!!detail?.requirements.length && (
            <div className="border-t border-dashed border-border pt-3">
              <div className="kicker mb-2">逐项核对</div>
              <ul className="space-y-1.5">
                {detail.requirements.map((r) => (
                  <li key={r.key}>
                    <label className="flex items-start gap-2 text-[12px]">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={!!checked[r.key]}
                        onChange={(e) => setChecked((prev) => ({ ...prev, [r.key]: e.target.checked }))}
                      />
                      <span>{r.label}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="border-t border-dashed border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
            复核确认仅代表解析内容与来源信息核对完成；后续索引处理按现有流水线规则执行，不代表索引必然成功。
          </p>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border px-6 py-4">
          <span className="text-[11px] text-muted-foreground">
            {error ? <span className="text-[hsl(4_72%_40%)]">{error}</span>
              : done ? '复核已提交'
              : detail?.pending ? `待复核 · revision ${detail.revision}${detail.issues.length ? ` · ${detail.issues.length} 项风险` : ''}`
              : '当前无需复核'}
          </span>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="ease-junyi rounded-md border border-border px-4 py-2 text-[12px] text-muted-foreground transition-colors duration-200 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
            >
              {done ? '关闭' : '暂不处理'}
            </button>
            {!done && (
              <button
                disabled={!detail?.pending || !detail.blocks.length || !detail.requirements.every((r) => checked[r.key])}
                onClick={async () => {
                  if (!detail) return
                  setError('')
                  try {
                    await api.post(`/api/documents/${doc.id}/review`, {
                      action: 'accept',
                      revision: detail.revision,
                      reviewer: user?.username || '未署名',
                      checks: Object.fromEntries((detail.requirements || []).map((r) => [r.key, true])),
                      note: '经界面复核确认',
                    })
                    markReviewed(doc.id)
                    setDone(true)
                    await refresh()
                  } catch (e) {
                    setError(e instanceof Error ? e.message : '复核提交失败')
                  }
                }}
                className="ease-junyi rounded-md bg-[hsl(12_74%_42%)] px-5 py-2 text-[12px] font-semibold text-[hsl(44_40%_97%)] transition-colors duration-200 hover:bg-[hsl(12_74%_38%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
              >
                确认完成复核
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

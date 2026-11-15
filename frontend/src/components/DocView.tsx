// 文档详情与原文预览（共享组件）
// 预览能力沿用现有实现：Word 展示节选段落（精确高亮不保证成功），
// Excel 展示结构化内容（暂不支持跳转原始单元格）。
import { useEffect, useState } from 'react'
import { Download, X } from 'lucide-react'
import { FormatMark, StatusBadge } from './bits'
import { downloadDemoFile, useSession } from '@/lib/session'
import { api } from '@/lib/api'
import type { Doc } from '@/lib/types'

const PIPELINE_STEPS = [
  { key: 'parsed', label: '解析' },
  { key: 'chunked', label: '切分' },
  { key: 'reviewed', label: '复核' },
  { key: 'indexed', label: '索引' },
] as const

export function PipelineRow({ doc }: { doc: Doc }) {
  return (
    <div className="flex items-center gap-0">
      {PIPELINE_STEPS.map((s, i) => {
        const done = doc.pipeline[s.key]
        const isReview = s.key === 'reviewed'
        const warn = isReview && !done
        return (
          <div key={s.key} className="flex items-center">
            {i > 0 && <span className="mx-2 h-px w-4 bg-border" />}
            <div className="flex items-center gap-1.5">
              <span
                className={`size-1.5 rounded-full ${
                  warn ? 'bg-[hsl(36_68%_38%)]' : 'bg-[hsl(148_32%_32%)]'
                }`}
              />
              <span
                className={`text-[11px] ${
                  warn ? 'font-medium text-[hsl(36_60%_30%)]' : 'text-muted-foreground'
                }`}
              >
                {s.label}
                {warn && '提示'}
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function DocPreviewDialog({
  doc,
  sourceRef,
  open,
  onClose,
}: {
  doc: Doc | null
  sourceRef?: {revision:number;index_token:string;chunk_id:string}
  open: boolean
  onClose: () => void
}) {
  const {user,kbId}=useSession()
  const [grantChecks,setGrantChecks]=useState<Record<string,boolean>>({})
  const [detail,setDetail]=useState<any>(null),[error,setError]=useState('')
  const sourceQuery=sourceRef?'?'+new URLSearchParams({revision:String(sourceRef.revision),index_token:sourceRef.index_token,chunk_id:sourceRef.chunk_id}).toString():''
  useEffect(()=>{let active=true;setDetail(null);setError('');setGrantChecks({});if(open&&doc){
    const url='/api/documents/'+encodeURIComponent(doc.id)+(sourceRef?'/source'+sourceQuery:'')
    api.get<any>(url).then(x=>{if(active)setDetail(sourceRef?{...x.document,matchedSource:x.source}:x)}).catch(e=>{if(active)setError(e.message)})
  }return()=>{active=false}},[open,doc?.id,sourceQuery])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open || !doc) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[hsl(36_16%_9%/0.55)] p-6 backdrop-blur-[2px]"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`文档预览：${doc.fileName}`}
    >
      <div
        className="flex max-h-[85vh] w-full max-w-2xl flex-col border border-border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-start gap-4 border-b border-border px-6 py-5">
          <FormatMark format={doc.format} className="mt-0.5" />
          <div className="min-w-0 flex-1">
            <div className="font-mono2 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              {doc.code} · {doc.version}
            </div>
            <h3 className="mt-1 break-all font-display text-[16px] font-semibold leading-snug">
              {doc.fileName}
            </h3>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <StatusBadge doc={doc} />
              <span className="text-[11px] text-muted-foreground">
                {doc.dept} · {doc.category}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="关闭预览"
            className="ease-junyi rounded-md p-2 text-muted-foreground transition-colors duration-200 hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* 内容 */}
        <div className="scrollbar-thin flex-1 overflow-y-auto px-6 py-5">
          <div className="flex items-center justify-between">
            <span className="kicker">{doc.format === 'xlsx' ? '结构化内容预览' : '原文节选预览'}</span>
            <span className="font-mono2 text-[10px] text-muted-foreground">服务端原文</span>
          </div>

          {error&&<p role="alert">{error}</p>}
          {!detail&&!error&&<p>正在核验来源…</p>}
          {detail&&<>
            {detail.result?.preview?.original&&<img className="mt-4 w-full" alt="服务端原文转换预览第1页" src={'/api/documents/'+doc.id+'/preview/original/1'+(sourceQuery||'?revision='+detail.revision)}/>}
            {detail.matchedSource&&<section className="mt-4 border p-3"><b>本次命中的来源片段（已核验版本与索引）</b><pre className="whitespace-pre-wrap text-sm">{detail.matchedSource.text}</pre><pre className="whitespace-pre-wrap text-xs">{JSON.stringify(detail.matchedSource.sources,null,2)}</pre></section>}
            <div className="mt-4 space-y-3">{(detail.result?.blocks||[]).map((b:any)=><section key={b.id}><b>{b.label||b.id}</b><pre className="whitespace-pre-wrap text-sm">{b.text}</pre></section>)}</div>
          </>}

          {user?.admin&&kbId==='demo'&&detail?.external_permission?.can_review&&<section className="mt-4 border p-4"><h4>本机外发许可审核</h4><p>仅适用于你已核实的完全虚构、公开、非机密资料。授予许可不代表本次已发送。</p>{[['fictional','我确认本文件完全虚构'],['no_sensitive_content','无敏感内容'],['third_party_terms_checked','已核对第三方分享权利'],['no_restricted_content','不包含受限内容']].map(([key,label])=><label className="block" key={key}><input type="checkbox" checked={!!grantChecks[key]} onChange={e=>setGrantChecks({...grantChecks,[key]:e.target.checked})}/>{label}</label>)}<button disabled={!['fictional','no_sensitive_content','third_party_terms_checked','no_restricted_content'].every(k=>grantChecks[k])} onClick={async()=>{try{await api.post('/api/documents/'+doc.id+'/external-permission',{revision:detail.revision,fingerprint:detail.external_permission.fingerprint,classification:'fictional',checks:{no_sensitive_content:true,third_party_terms_checked:true,no_restricted_content:true}});setDetail(await api.get('/api/documents/'+doc.id));setGrantChecks({})}catch(e){setError((e as Error).message)}}}>逐份授予外发许可</button></section>}

          {/* 能力边界说明（真实约束，不虚构） */}
          <div className="mt-6 space-y-1.5 border-t border-dashed border-border pt-4 text-[11px] leading-relaxed text-muted-foreground">
            {doc.format === 'docx' && (
              <p>· Word 预览展示解析后的节选内容，原文精确高亮定位不保证成功。</p>
            )}
            {doc.format === 'xlsx' && (
              <p>· Excel 支持结构化内容查看，暂不支持从检索结果精确跳转到原始单元格。</p>
            )}
            {doc.status === 'archived' && (
              <p>· 本文档已废止，仅供授权范围内历史归档查看，不参与检索与问答证据选择。</p>
            )}
            {doc.indexStatus === 'review-pending' && (
              <p>· 该文档存在结构化解析复核提示，检索结果以服务端返回为准。</p>
            )}
          </div>
        </div>

        {/* 底部操作 */}
        <div className="flex items-center justify-between border-t border-border px-6 py-4">
          <PipelineRow doc={doc} />
          <button
            onClick={() => downloadDemoFile(doc)}
            className="ease-junyi flex items-center gap-2 rounded-md border border-border bg-card px-4 py-2 text-[12px] font-medium transition-colors duration-200 hover:border-[hsl(12_74%_42%/0.5)] hover:text-[hsl(12_74%_42%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
          >
            <Download className="size-3.5" />
            下载原文件
          </button>
        </div>
      </div>
    </div>
  )
}

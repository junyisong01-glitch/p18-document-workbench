// 文档详情与原文预览（共享组件）
// 预览能力沿用现有实现：Word 展示节选段落（精确高亮不保证成功），
// Excel 展示结构化内容（暂不支持跳转原始单元格）。
import { useEffect, useRef, useState } from 'react'
import * as PreviewDialog from '@radix-ui/react-dialog'
import { Download, X } from 'lucide-react'
import { FormatMark, StatusBadge } from './bits'
import { downloadDemoFile, useSession } from '@/lib/session'
import { api } from '@/lib/api'
import { OriginalBlock, OriginalTable, type SourceBlock, type SourceTable } from './SourceContent'
import { ExcelPreview, type ExcelMatch, type ExcelSheet } from './ExcelPreview'
import { sourcePages, locationLabel, originalRange, type SourceLocation } from '@/lib/source-presentation'
import type { Doc } from '@/lib/types'
import { documentTitleParts } from '../lib/document-title'

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
        const warn = isReview && !!doc.reviewRequired && !done
        return (
          <div key={s.key} className="flex items-center">
            {i > 0 && <span className="mx-2 h-px w-4 bg-border" />}
            <div className="flex items-center gap-1.5">
              <span
                className={`size-1.5 rounded-full ${
                  warn ? 'bg-[hsl(36_68%_38%)]' : done ? 'bg-[hsl(148_32%_32%)]' : 'bg-border'
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
  drawer = false,
  open,
  onClose,
}: {
  doc: Doc | null
  sourceRef?: {revision:number;index_token:string;chunk_id:string}
  drawer?: boolean
  open: boolean
  onClose: () => void
}) {
  const {user,kbId}=useSession()
  const [grantChecks,setGrantChecks]=useState<Record<string,boolean>>({})
  const [detail,setDetail]=useState<any>(null),[error,setError]=useState('')
  const [tab,setTab]=useState<'evidence'|'original'|'full'>('evidence')
  const [page,setPage]=useState(1),[pages,setPages]=useState<number|null>(null)
  const [previewError,setPreviewError]=useState('')
  const [imageError,setImageError]=useState(false)
  const firstMatch=useRef<HTMLDivElement>(null)
  const opener=useRef<HTMLElement|null>(null)
  const sourceQuery=sourceRef?'?'+new URLSearchParams({revision:String(sourceRef.revision),index_token:sourceRef.index_token,chunk_id:sourceRef.chunk_id}).toString():''
  useEffect(()=>{let active=true;setDetail(null);setError('');setGrantChecks({});setTab(sourceRef?'evidence':'original');setPages(null);setPreviewError('');setImageError(false);setPage(1);if(open&&doc){
    const url='/api/documents/'+encodeURIComponent(doc.id)+(sourceRef?'/source'+sourceQuery:'')
    api.get<any>(url).then(x=>{
      if (!active) return
      setDetail(sourceRef?{...x.document,matchedSource:x.source}:x)
      const locations:SourceLocation[]=x.source?.sources||[]
      setPage(sourcePages(locations)[0]||1)
      const full:SourceBlock[]=x.document?.result?.blocks||[]
      const sheets:ExcelSheet[]=(sourceRef?x.document:x)?.result?.excel_sheets||[]
      if(doc.format==='xlsx'&&sheets.length||drawer&&sourceRef&&full.some(block=>locations.some(location=>location.block_id===block.id)))setTab('full')
    }).catch(e=>{if(active)setError(e.message)})
  }return()=>{active=false}},[open,doc?.id,doc?.format,sourceQuery,drawer])

  useEffect(() => {
    if (!open || !doc || !detail || tab !== 'original') return
    let active=true
    setPages(null);setPreviewError('');setImageError(false)
    if (!detail.result?.preview?.original) {setPreviewError('此文件尚无分页预览，可查看全文解析或下载原件。');return}
    api.get<{pages:number}>('/api/documents/'+encodeURIComponent(doc.id)+'/preview/original/meta'+(sourceQuery||'?revision='+detail.revision))
      .then(meta=>{if(active){setPages(meta.pages);setPage(p=>p<=meta.pages?p:1)}})
      .catch(e=>{if(active)setPreviewError(e.message)})
    return()=>{active=false}
  },[open,doc?.id,detail,tab,sourceQuery])

  useEffect(() => {
    if (!open || drawer) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {e.preventDefault();e.stopImmediatePropagation();onClose()}
    }
    window.addEventListener('keydown', onKey, true)
    return () => window.removeEventListener('keydown', onKey, true)
  }, [open, drawer, onClose])

  useEffect(()=>{
    if (!open || !drawer || tab!=='full' || !sourceQuery || !detail) return
    firstMatch.current?.scrollIntoView({block:'center'})
  },[open,drawer,tab,sourceQuery,detail])

  if (!open || !doc) return null
  const matched=detail?.matchedSource
  const sources:SourceLocation[]=matched?.sources||[]
  const blocks:(SourceBlock & { sheet?:string; row_start?:number; row_end?:number; table_id?:string|null })[]=detail?.result?.blocks||[]
  const excelSheets:ExcelSheet[]=doc.format==='xlsx' ? detail?.result?.excel_sheets||[] : []
  const excelMatches:ExcelMatch[]=excelSheets.length ? sources.flatMap(location=>{
    const block=blocks.find(item=>item.id===location.block_id)
    const sheet=location.sheet??block?.sheet
    const start=location.row_start??block?.row_start
    if(!sheet||start==null)return []
    return [{sheet,start,end:location.row_end??block?.row_end??start,tableId:block?.table_id}]
  }) : []
  const tables:SourceTable[]=matched?.tables||[]
  const mappedPages=sourcePages(sources)
  const matchedBlocks=new Set(drawer?sources.map(source=>source.block_id):[])
  const firstMatchedBlock=blocks.find(block=>matchedBlocks.has(block.id))?.id
  const { title } = documentTitleParts(doc.fileName)
  const label=`文档预览：${title}`
  const content=<>
        {/* 头部 */}
        <div className="flex items-start gap-4 border-b border-border px-6 py-5">
          <FormatMark format={doc.format} className="mt-0.5" />
          <div className="min-w-0 flex-1">
            <div className="font-mono2 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              {doc.code} · 文档版本 {doc.version}
            </div>
            <h3 className="mt-1 break-all font-display text-[16px] font-semibold leading-snug">
              {title}
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
        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">
          <div role="tablist" aria-label="来源查看方式" onKeyDown={e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();const tabs=Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('[role=tab]'));const current=tabs.indexOf(document.activeElement as HTMLButtonElement);const next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(current+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;tabs[next]?.focus();tabs[next]?.click()}} className="mb-5 flex flex-wrap gap-1 border-b border-border">
            {([['evidence','命中证据'],['original','原文件'],['full',excelSheets.length?'工作表预览':'全文解析']] as const)
              .filter(([key])=>(key!=='evidence'||!!sourceRef)&&(key!=='original'||!excelSheets.length))
              .map(([key,label])=><button key={key} role="tab" tabIndex={tab===key?0:-1} aria-selected={tab===key} aria-controls="source-panel" id={'source-tab-'+key} onClick={()=>setTab(key)} className={`border-b-2 px-4 py-3 text-[13px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${tab===key?'border-[hsl(12_74%_42%)] font-semibold text-[hsl(12_74%_38%)]':'border-transparent text-muted-foreground hover:text-foreground'}`}>{label}</button>)}
          </div>
          {error&&<p role="alert">{error}</p>}
          {!detail&&!error&&<p role="status">正在核验来源…</p>}
          {detail&&<div id="source-panel" role="tabpanel" aria-labelledby={'source-tab-'+tab} className="space-y-4">
            {tab==='evidence'&&matched&&<>
              <div className="space-y-2 border-l-2 border-[hsl(12_74%_42%/0.55)] pl-4">
                <h4 className="text-[16px] font-semibold">{matched.section||'本次命中证据'}</h4>
                <p className="text-[12px] leading-relaxed text-muted-foreground">来源、文档修订及索引已由服务端核验；以下保留实际命中内容，不生成答案。</p>
              </div>
              <div className="space-y-3" data-testid="matched-evidence">
                {tables.length? <>
                  {sources.map((source,i)=>{const block=blocks.find(b=>b.id===source.block_id);return block&&block.kind!=='table'&&originalRange(block.text,source).trim()&&originalRange(block.text,source).trim()!==matched.section?.trim()?<OriginalBlock key={i} block={{...block,text:originalRange(block.text,source)}}/>:null})}
                  {tables.map((table,i)=><OriginalTable key={i} table={table}/>)}
                </>:<p className="whitespace-pre-wrap text-[14px] leading-[1.9] [overflow-wrap:anywhere]">{matched.text}</p>}
              </div>
              <section className="border-t border-border pt-4">
                <h4 className="text-[12px] font-semibold">原文位置</h4>
                <ul className="mt-2 space-y-2 text-[12px] leading-relaxed text-muted-foreground">{sources.map((source,i)=><li key={i}>{locationLabel(source)}</li>)}</ul>
                {excelSheets.length>0?<button onClick={()=>setTab('full')} className="mt-3 text-[12px] font-medium text-[hsl(12_74%_38%)] underline underline-offset-4">在工作表查看命中行</button>:
                  mappedPages.length>0&&<button onClick={()=>{setPage(mappedPages[0]);setTab('original')}} className="mt-3 text-[12px] font-medium text-[hsl(12_74%_38%)] underline underline-offset-4">打开对应原件预览页</button>}
              </section>
              <details className="border-t border-border pt-3 text-[12px] text-muted-foreground"><summary className="cursor-pointer py-1">技术来源信息与检索原始文本</summary>
                <p className="my-2">片段 ID：<span className="break-all font-mono2">{sourceRef?.chunk_id}</span> · 文档修订 {sourceRef?.revision}</p>
                <pre className="whitespace-pre-wrap break-words leading-relaxed">{matched.text}</pre>
                <pre className="mt-3 whitespace-pre-wrap break-words">{JSON.stringify(sources,null,2)}</pre>
              </details>
            </>}
            {tab==='original'&&<>
              {doc.format!=='xlsx'&&<p className="text-[12px] leading-relaxed text-muted-foreground">{doc.format==='pdf'?'原始 PDF 分页预览。':'原件转换后的分页预览；版式可能与本机 Office 存在差异。'}{mappedPages.length?` 已记录的来源页：${mappedPages.join('、')}。`:' 未记录精确页映射，从第1页开始。'}不保证逐字高亮。</p>}
              {previewError&&<p role="alert" className="rounded-sm border border-border p-4 text-[13px]">{previewError}</p>}
              {!pages&&!previewError&&<p role="status">正在读取预览页数…</p>}
              {pages&&<>
                <div className="flex flex-wrap items-center gap-3 text-[12px]">
                  <button disabled={page<=1} onClick={()=>{setPage(p=>p-1);setImageError(false)}} className="rounded-sm border border-border px-3 py-1.5 disabled:opacity-40">上一页</button>
                  <label>第 <select aria-label="原件预览页码" value={page} onChange={e=>{setPage(Number(e.target.value));setImageError(false)}} className="mx-1 border border-border bg-card px-2 py-1">{Array.from({length:pages},(_,i)=><option value={i+1} key={i}>{i+1}</option>)}</select> / {pages} 页</label>
                  <button disabled={page>=pages} onClick={()=>{setPage(p=>p+1);setImageError(false)}} className="rounded-sm border border-border px-3 py-1.5 disabled:opacity-40">下一页</button>
                </div>
                {imageError?<p role="alert">原件预览加载失败，请重新打开预览或下载原件核对。</p>:<img key={page} onError={()=>setImageError(true)} className="w-full border border-border bg-white" alt={'服务端原文转换预览第'+page+'页'} src={'/api/documents/'+encodeURIComponent(doc.id)+'/preview/original/'+page+(sourceQuery||'?revision='+detail.revision)}/>}
              </>}
            </>}
            {tab==='full'&&(excelSheets.length ? <ExcelPreview key={doc.id+sourceQuery} sheets={excelSheets} matches={excelMatches}/> : <>
              <p className="border-b border-border pb-3 text-[12px] leading-relaxed text-muted-foreground">以下是整份文档的解析内容，包含未命中的其他段落；不能全部当作本题命中证据。表格按实际行列显示。</p>
              {firstMatchedBlock&&<p className="text-xs text-[hsl(12_74%_38%)]">命中章节 · {matched?.section||'本次命中证据'}</p>}
              <div className="space-y-4">{blocks.map(block=>matchedBlocks.has(block.id)?
                <div key={block.id} ref={block.id===firstMatchedBlock?firstMatch:undefined} data-matched-section
                  className="rounded-r-md border-l-2 border-primary bg-primary/5 px-3 py-2"><OriginalBlock block={block}/></div>:
                <OriginalBlock key={block.id} block={block}/>
              )}</div>
            </>)}
          </div>}

          {user?.admin&&kbId==='demo'&&detail?.external_permission?.can_review&&<section className="mt-4 border p-4"><h4>本机外发许可审核</h4><p>仅适用于你已核实的完全虚构、公开、非机密资料。授予许可不代表本次已发送。</p>{[['fictional','我确认本文件完全虚构'],['no_sensitive_content','无敏感内容'],['third_party_terms_checked','已核对第三方分享权利'],['no_restricted_content','不包含受限内容']].map(([key,label])=><label className="block" key={key}><input type="checkbox" checked={!!grantChecks[key]} onChange={e=>setGrantChecks({...grantChecks,[key]:e.target.checked})}/>{label}</label>)}<button disabled={!['fictional','no_sensitive_content','third_party_terms_checked','no_restricted_content'].every(k=>grantChecks[k])} onClick={async()=>{try{await api.post('/api/documents/'+doc.id+'/external-permission',{revision:detail.revision,fingerprint:detail.external_permission.fingerprint,classification:'fictional',checks:{no_sensitive_content:true,third_party_terms_checked:true,no_restricted_content:true}});setDetail(await api.get('/api/documents/'+doc.id));setGrantChecks({})}catch(e){setError((e as Error).message)}}}>逐份授予外发许可</button></section>}

          {/* 能力边界说明（真实约束，不虚构） */}
          <div className="mt-6 space-y-1.5 border-t border-dashed border-border pt-4 text-[11px] leading-relaxed text-muted-foreground">
            {doc.format === 'docx' && (
              <p>· Word 预览展示解析后的节选内容，原文精确高亮定位不保证成功。</p>
            )}
            {doc.format === 'xlsx' && !excelSheets.length && (
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
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-4 sm:px-6">
          <PipelineRow doc={doc} />
          <button
            onClick={() => {if(!sourceRef){downloadDemoFile(doc);return}const link=document.createElement('a');link.href='/api/documents/'+encodeURIComponent(doc.id)+'/file/original'+sourceQuery;link.download=doc.fileName;link.click()}}
            className="ease-junyi flex items-center gap-2 rounded-md border border-border bg-card px-4 py-2 text-[12px] font-medium transition-colors duration-200 hover:border-[hsl(12_74%_42%/0.5)] hover:text-[hsl(12_74%_42%)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
          >
            <Download className="size-3.5" />
            下载原文件
          </button>
        </div>
  </>
  if(drawer)return <PreviewDialog.Root open onOpenChange={value=>{if(!value)onClose()}}>
    <PreviewDialog.Portal>
      <PreviewDialog.Overlay className="fixed inset-0 z-50 bg-foreground/15"/>
      <PreviewDialog.Content aria-describedby={undefined} data-testid="qa-document-drawer"
        onOpenAutoFocus={()=>{opener.current=document.activeElement instanceof HTMLElement?document.activeElement:null}}
        onCloseAutoFocus={event=>{event.preventDefault();opener.current?.focus()}}
        className="fixed inset-y-0 right-0 z-50 flex h-dvh w-full max-w-[36rem] flex-col border-l border-border bg-card shadow-2xl outline-none motion-safe:animate-in motion-safe:slide-in-from-right motion-safe:duration-200">
        <PreviewDialog.Title className="sr-only">{label}</PreviewDialog.Title>
        {content}
      </PreviewDialog.Content>
    </PreviewDialog.Portal>
  </PreviewDialog.Root>
  return <div className="fixed inset-0 z-50 flex items-center justify-center bg-[hsl(36_16%_9%/0.55)] p-6 backdrop-blur-[2px]"
    onClick={onClose} role="dialog" aria-modal="true" aria-label={label}>
    <div className="flex max-h-[85vh] w-full max-w-4xl flex-col border border-border bg-card shadow-2xl"
      onClick={event=>event.stopPropagation()}>{content}</div>
  </div>
}

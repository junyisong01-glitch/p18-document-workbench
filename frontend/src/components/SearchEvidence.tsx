import {useEffect,useState} from 'react'
import {api} from '@/lib/api'
import {useSession} from '@/lib/session'
import {OriginalTable,type SourceBlock,type SourceTable} from './SourceContent'
import {ExcelCitationEvidence,type ExcelEvidenceBlock,type ExcelSheet} from './ExcelPreview'
import {originalRange,type SourceLocation} from '@/lib/source-presentation'
import './SearchEvidence.css'

export type MatchedSource={text:string;section?:string;tables?:SourceTable[];sources?:SourceLocation[]}
type SourceResponse={source:MatchedSource;document:{result?:{blocks?:(SourceBlock&ExcelEvidenceBlock)[];excel_sheets?:ExcelSheet[]}}}

export function MatchedSearchContent({source,blocks}:{source:MatchedSource;blocks:SourceBlock[]}){
 const tables=source.tables||[]
 if(!tables.length)return <div className="se-paragraphs">{source.text.split(/\n{2,}/).map((text,i)=><p key={i}>{text}</p>)}</div>
 // Only the chunk's actual tables are shown. Full-document tables may contain
 // unmatched rows and must never be substituted into a search result.
 const paragraphs=(source.sources||[]).flatMap(location=>{
  const block=blocks.find(block=>block.id===location.block_id)
  if(!block||block.kind==='table')return []
  const text=originalRange(block.text,location)
  return text.trim()&&text.trim()!==source.section?.trim()?[text]:[]
 })
 return <>{paragraphs.length>0&&<div className="se-paragraphs">{paragraphs.map((text,i)=><p key={i}>{text}</p>)}</div>}
 <div className="se-tables">{tables.map((table,i)=><section key={i} className="se-table" data-columns={table.rows[0]?.length} data-plain-grid={!table.cells?.some(cell=>(cell.colspan||1)>1||(cell.rowspan||1)>1)}><OriginalTable table={table} scrollLabel={`命中证据原文表格 ${i+1}，可左右滚动`}/></section>)}</div>
 <p className="se-scroll-hint">表格可左右滑动，内容保留原始行列。</p>
 <details className="se-raw"><summary>查看检索原始文本</summary><pre>{source.text}</pre></details></>
}

export function SearchEvidence({documentId,sourceRef,compactSpreadsheet}:{
 documentId:string
 sourceRef?:{revision:number;index_token:string;chunk_id:string}
 compactSpreadsheet?:boolean
}){
 const {kbId,user}=useSession()
 const query=sourceRef?new URLSearchParams({revision:String(sourceRef.revision),index_token:sourceRef.index_token,chunk_id:sourceRef.chunk_id}).toString():''
 const key=JSON.stringify([kbId,user?.username,documentId,query])
 const [retry,setRetry]=useState(0),[state,setState]=useState<{key:string;data?:SourceResponse;error?:string}>({key:''})
 useEffect(()=>{
  let active=true;setState({key})
  if(!query){setState({key,error:'来源标识不完整，请重新检索。'});return}
  api.get<SourceResponse>('/api/documents/'+encodeURIComponent(documentId)+'/source?'+query)
   .then(data=>{if(active)setState({key,data})})
   .catch(()=>{if(active)setState({key,error:'暂时无法核验来源。资料可能已变化或不可访问，请重新检索；也可重试加载。'})})
  return()=>{active=false}
 },[key,retry,documentId,query])
 const current=state.key===key?state:undefined
 if(current?.error)return <div className="se-error" role="status"><p>{current.error}</p><button type="button" onClick={()=>setRetry(value=>value+1)}>重试加载来源</button></div>
 if(!current?.data)return <p className="se-loading" role="status">正在核验命中来源…</p>
 const {source,document}=current.data
 const blocks=document.result?.blocks||[]
 const fallback=<MatchedSearchContent source={source} blocks={blocks}/>
 return compactSpreadsheet?<ExcelCitationEvidence sheets={document.result?.excel_sheets||[]}
  locations={source.sources||[]} blocks={blocks} fallback={fallback}/>:fallback
}

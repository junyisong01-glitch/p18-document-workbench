import { useEffect, useRef, useState } from 'react'

type ExcelCell = { coordinate: string; text: string; warning?: string; formula_cached?: boolean }
type ExcelRow = { row: number; cells: ExcelCell[] }
type ExcelTableData = {
  id: string
  range: string
  headers: string[]
  header_confirmed: boolean
  rows: ExcelRow[]
  summary_rows: ExcelRow[]
}
export type ExcelSheet = { name: string; metadata: ExcelRow[]; tables: ExcelTableData[]; other_rows: ExcelRow[] }
export type ExcelMatch = { sheet: string; start: number; end: number; tableId?: string | null }

const rowLimit = 40
const matchesRow = (match: ExcelMatch, row: number) => match.start <= row && row <= match.end

function CellText({ cell }: { cell: ExcelCell }) {
  const hint=cell.warning || (cell.formula_cached?'公式的已保存结果':undefined)
  return <span title={hint ? `${cell.coordinate} · ${hint}` : cell.coordinate}>
    {cell.text}{cell.warning&&<small className="mt-1 block text-amber-800">{cell.warning}</small>}
  </span>
}

function SpreadsheetTable({ table, sheetName, matches, initialRow }: {
  table: ExcelTableData; sheetName: string; matches: ExcelMatch[]; initialRow?: number
}) {
  const records=[...table.rows,...table.summary_rows].sort((a,b)=>a.row-b.row)
  const indexOfMatch=records.findIndex(record=>record.row===initialRow)
  const [page,setPage]=useState(Math.max(0,Math.floor(indexOfMatch/rowLimit)))
  const target=useRef<HTMLTableRowElement>(null)
  useEffect(()=>{
    target.current?.scrollIntoView({block:'nearest',inline:'nearest'})
  },[])
  const current=records.slice(page*rowLimit,(page+1)*rowLimit)
  const isLarge=records.length>rowLimit
  const heading=`${sheetName} ${table.range}`

  return <section className="space-y-2">
    <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-muted-foreground">
      <span>{table.range} · {records.length} 行</span>
      {!table.header_confirmed&&<span className="text-amber-800">表头待核对</span>}
    </div>
    <div tabIndex={0} role="region" aria-label={`滚动查看 ${heading}`}
      className="max-h-[min(56dvh,32rem)] overflow-auto rounded-md border border-border focus-visible:outline-primary">
      <table className="w-full border-separate border-spacing-0 text-left text-[13px]">
        <caption className="sr-only">{heading}</caption>
        <thead className="sticky top-0 z-[1] bg-secondary">
          <tr>
            <th scope="col" className="border-b border-border px-2.5 py-2 text-xs font-medium">行</th>
            {table.headers.map((header,index)=><th key={index} scope="col"
              className="whitespace-nowrap border-b border-l border-border px-3 py-2 font-semibold">{header}</th>)}
          </tr>
        </thead>
        <tbody>{current.map(record=>{
          const matched=matches.some(match=>matchesRow(match,record.row))
          return <tr key={record.row} ref={record.row===initialRow?target:undefined} data-matched-section={matched||undefined}
            className={matched?'bg-primary/10':'even:bg-secondary/25'}>
            <th scope="row" className="border-b border-border px-2.5 py-1.5 text-right text-[11px] font-normal tabular-nums text-muted-foreground">
              {matched&&<span className="sr-only">命中行 </span>}{record.row}
            </th>
            {table.headers.map((_,index)=><td key={index} className="whitespace-pre-wrap border-b border-l border-border px-3 py-1.5 align-top">
              {record.cells[index]&&<CellText cell={record.cells[index]}/>}
            </td>)}
          </tr>
        })}</tbody>
      </table>
    </div>
    {isLarge&&<nav aria-label={`${heading} 分页`} className="flex flex-wrap items-center justify-end gap-2 text-xs">
      <button type="button" className="rounded border border-border px-2 py-1 disabled:opacity-40"
        disabled={page===0} onClick={()=>setPage(value=>value-1)}>上一组</button>
      <span role="status">{current[0]?.row}–{current.at(-1)?.row} 行</span>
      <button type="button" className="rounded border border-border px-2 py-1 disabled:opacity-40"
        disabled={(page+1)*rowLimit>=records.length} onClick={()=>setPage(value=>value+1)}>下一组</button>
    </nav>}
  </section>
}

export function ExcelPreview({ sheets, matches }: { sheets: ExcelSheet[]; matches: ExcelMatch[] }) {
  const primary=matches.find(match=>sheets.some(sheet=>sheet.name===match.sheet))
  const [name,setName]=useState(primary?.sheet ?? sheets[0]?.name)
  const sheet=sheets.find(item=>item.name===name) ?? sheets[0]
  if(!sheet)return null
  const localMatches=matches.filter(match=>match.sheet===sheet.name)

  return <section className="min-w-0 space-y-4" aria-label="工作表预览">
    <header>
      <p className="text-xs text-muted-foreground">工作表预览使用 Excel 已读取的数据，原始格式及公式可下载原文件核对。</p>
      {sheets.length>1&&<nav aria-label="切换工作表" className="mt-3 flex flex-wrap gap-2">
        {sheets.map(item=><button type="button" key={item.name} aria-pressed={item.name===sheet.name}
          className="rounded-md border border-border px-3 py-1.5 text-xs aria-pressed:border-primary aria-pressed:bg-primary/10"
          onClick={()=>setName(item.name)}>{item.name}</button>)}
      </nav>}
    </header>
    <div className="space-y-1">
      <h4 className="text-sm font-semibold">{sheet.name}</h4>
      {sheet.metadata.length>0&&<div className="space-y-1 text-xs leading-6 text-muted-foreground">
        {sheet.metadata.map(record=><p key={record.row}>
          {record.cells.map((cell,index)=><span key={cell.coordinate}>{index>0?' · ':''}<CellText cell={cell}/></span>)}
        </p>)}
      </div>}
    </div>
    {sheet.tables.map(table=>{
      const tableMatches=localMatches.filter(match=>match.tableId===table.id)
      const firstMatch=tableMatches[0]
      return <SpreadsheetTable key={`${sheet.name}/${table.id}`} table={table} sheetName={sheet.name}
        matches={tableMatches} initialRow={firstMatch===primary?firstMatch?.start:undefined}/>
    })}
    {sheet.other_rows.length>0&&<details open={sheet.tables.length===0} className="rounded-md border border-border px-3 py-2">
      <summary className="cursor-pointer text-xs font-medium">其他单元格 · {sheet.other_rows.length} 行</summary>
      <dl className="mt-2 max-h-72 divide-y divide-border overflow-auto text-xs">
        {sheet.other_rows.map(record=><div key={record.row}
          data-matched-section={localMatches.some(match=>!match.tableId&&matchesRow(match,record.row))||undefined}
          className="flex flex-wrap gap-3 py-2 data-[matched-section]:bg-primary/10">
          <dt className="text-muted-foreground">第 {record.row} 行</dt>
          <dd className="flex min-w-0 flex-wrap gap-x-4 gap-y-1">{record.cells.map(cell=><span key={cell.coordinate}>
            <span className="mr-1 text-muted-foreground">{cell.coordinate}</span><CellText cell={cell}/>
          </span>)}</dd>
        </div>)}
      </dl>
    </details>}
    {!sheet.tables.length&&!sheet.other_rows.length&&<p className="text-xs text-muted-foreground">这个工作表没有其他可显示的单元格。</p>}
  </section>
}

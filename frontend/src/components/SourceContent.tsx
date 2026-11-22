interface TableCell {
  row: number
  column: number
  rowspan?: number
  colspan?: number
  text: string
}
export interface SourceTable {
  rows: (string | null)[][]
  cells?: TableCell[]
}
export interface SourceBlock {
  id: string
  kind: string
  text: string
  label?: string
  section?: string
  style?: string
  line_start?: number
  line_end?: number
  heading_level?: number
  tables?: SourceTable[]
  cells?: { coordinate: string; text: string; warning?: string }[]
}

export function OriginalTable({ table,scrollLabel }: { table: SourceTable;scrollLabel?:string }) {
  return <div tabIndex={scrollLabel?0:undefined} role={scrollLabel?'region':undefined} aria-label={scrollLabel} className="my-3 max-w-full overflow-x-auto rounded-sm border border-border">
    <table className="w-full min-w-[28rem] border-collapse text-left text-[13px] leading-relaxed">
      <caption className="sr-only">原文表格（保留原始行列及合并单元格）</caption>
      {scrollLabel&&<colgroup>{table.rows[0]?.map((_,i)=><col key={i}/>)}</colgroup>}
      <tbody>{table.rows.map((row, ri) => <tr key={ri} className={ri===0?'bg-secondary/65 font-medium':ri % 2 ? 'bg-secondary/25' : ''}>
        {row.map((value, ci) => {
          const cell = table.cells?.find(c => c.row === ri + 1 && c.column === ci + 1)
          // None 是原始合并区域的延续，不能伪造新单元格或重复金额。
          if (value === null && !cell) return null
          return <td key={ci} rowSpan={cell?.rowspan || 1} colSpan={cell?.colspan || 1}
            className="whitespace-pre-wrap border border-border px-3 py-2 align-top [overflow-wrap:anywhere]">
            {cell?.text ?? value}
          </td>
        })}
      </tr>)}</tbody>
    </table>
  </div>
}

export function OriginalBlock({ block }: { block: SourceBlock }) {
  if (!block.text.trim()) return null
  if (block.kind === 'table' && block.tables?.length) {
    return <section>{block.section && <h4 className="text-[12px] font-medium text-muted-foreground">{block.section} · 原文表格</h4>}
      {block.tables.map((table, i) => <OriginalTable table={table} key={i} />)}
    </section>
  }
  if (block.cells?.length) return <section className="space-y-2">
    <h4 className="text-[12px] font-medium text-muted-foreground">{block.label || block.section}</h4>
    <p className="whitespace-pre-wrap text-[13px] leading-relaxed [overflow-wrap:anywhere]">{block.text}</p>
    <details className="text-[12px] text-muted-foreground"><summary className="cursor-pointer py-2">查看原始单元格与已保存值</summary>
      <dl className="divide-y divide-border">{block.cells.map(cell => <div key={cell.coordinate} className="grid grid-cols-[5rem_1fr] gap-3 py-2">
        <dt className="font-mono2">{cell.coordinate}</dt><dd className="whitespace-pre-wrap break-words">{cell.text}{cell.warning && <span className="block text-[hsl(36_60%_30%)]">{cell.warning}</span>}</dd>
      </div>)}</dl>
    </details>
  </section>
  if(block.style==='Code')return <pre className="overflow-x-auto whitespace-pre rounded-sm bg-secondary p-3 text-[13px]"><code>{block.text}</code></pre>
  if (block.heading_level || block.text.trim() === block.section?.trim()) {
    return <h4 className="pt-2 font-display text-[16px] font-semibold leading-relaxed">{block.text}</h4>
  }
  return <p className="whitespace-pre-wrap text-[14px] leading-[1.9] [overflow-wrap:anywhere]">{block.text}</p>
}

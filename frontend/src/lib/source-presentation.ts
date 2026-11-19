// 只整理服务端已验证的原文坐标，不生成事实或改变检索结果。
export interface SourceLocation {
  block_id: string
  label?: string
  variant?: string
  preview_pages?: Record<string, number>
  page?: number
  sheet?: string
  row_start?: number
  row_end?: number
  raw_start?: number
  raw_end?: number
}

export function sourcePages(sources: SourceLocation[]): number[] {
  return [...new Set(sources.map(s => s.preview_pages?.original ?? s.page)
    .filter((p): p is number => Number.isInteger(p) && Number(p) > 0))].sort((a, b) => a - b)
}

export function locationLabel(source: SourceLocation): string {
  const page = sourcePages([source])[0]
  const row = source.row_start == null ? '' : `第${source.row_start}${source.row_end && source.row_end !== source.row_start ? `—${source.row_end}` : ''}行`
  return [source.label || source.block_id, source.sheet ? `工作表「${source.sheet}」` : '', row, page ? `原件预览第${page}页` : ''].filter(Boolean).join(' · ')
}

export function originalRange(text: string, source: SourceLocation): string {
  // 后端原文范围按 Python Unicode 字符计数；不能用 JS UTF-16 下标截取。
  return Array.from(text).slice(source.raw_start ?? 0, source.raw_end).join('')
}

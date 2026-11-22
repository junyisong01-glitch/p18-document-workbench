const importedTitleSuffixes = new Map([
  ['EXT-02', '（最终修正版）'],
  ['EXT-05', '（修正版）'],
  ['EXT-06', '（修正版）'],
  ['EXT-07', '（修正版）'],
  ['EXT-08', '（修正版）'],
  ['EXT-10', '（定点修正版）'],
  ['EXT-11', '（定点修正版）'],
  ['EXT-12', '（定点修正版）'],
  ['EXT-13', '（定点修正版）'],
  ['EXT-14', '（最终修正版）'],
])

/** Format a display title while keeping the stored name available to callers. */
export function documentTitleParts(name: string): { title: string; number: string } {
  const leadingNumber = /^((?:EXT[-–]\d+|QC(?:[-–][A-Z]+)+[-–]\d+))[ _\u3000]+(?=\S)/i.exec(name)
  const number = leadingNumber?.[1] ?? ''
  const stem = name.slice(leadingNumber?.[0].length ?? 0)
  const title = stem.replace(/(\S)\.(?:docx?|xlsx?|pdf|pptx?|csv|md|txt)$/i, '$1').replace(/_+/g, ' ')
  const suffix = importedTitleSuffixes.get(number)
  if (!suffix || !title.endsWith(suffix)) return { title, number }
  const shortTitle = title.slice(0, -suffix.length).replace(/^(V\d+(?:\.\d+)+|BUG-\d+)(?=[\u4e00-\u9fff])/, '$1 ')
  return { title: shortTitle || title, number }
}

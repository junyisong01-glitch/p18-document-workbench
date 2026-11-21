import { useState } from 'react'
import { api } from '@/lib/api'

type Settings = {
  enabled: boolean
  revision: number
  public_ids: string[]
  documents: { id: string; name: string }[]
}
type Audit = {
  at: number
  username: string
  question: string
  event: string
  document_ids: string[]
  blocked: boolean
  reason?: string
  sent?: string
}

export function ExternalModelAdmin({ onChanged }: { onChanged: () => void }) {
  const [settings, setSettings] = useState<Settings>()
  const [rows, setRows] = useState<Audit[] | null>(null)
  const [username, setUsername] = useState('')
  const [date, setDate] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function load() {
    setError('')
    try { setSettings(await api.get<Settings>('/api/rag/external-settings')) }
    catch (cause) { setError((cause as Error).message) }
  }

  async function save(enabled: boolean, publicIds: string[]) {
    if (!settings || busy) return
    setBusy(true)
    setError('')
    try {
      const next = await api.put<Omit<Settings, 'documents'>>('/api/rag/external-settings', {
        enabled, public_ids: publicIds, revision: settings.revision,
      })
      setSettings({ ...settings, ...next })
      onChanged()
    } catch (cause) { setError((cause as Error).message) }
    finally { setBusy(false) }
  }

  async function filter(event: React.FormEvent) {
    event.preventDefault()
    setError('')
    const filters = new URLSearchParams()
    if (username.trim()) filters.set('username', username.trim())
    if (date) {
      const from = new Date(date + 'T00:00:00')
      const next = new Date(from)
      next.setDate(next.getDate() + 1)
      filters.set('start', String(from.getTime() / 1000))
      filters.set('end', String((next.getTime() - 1) / 1000))
    }
    try { setRows(await api.get<Audit[]>('/api/rag/external-audit?' + filters)) }
    catch (cause) { setError((cause as Error).message) }
  }

  return <details className="rounded-lg border border-border bg-card p-5" onToggle={event => { if (event.currentTarget.open) void load() }}>
    <summary className="cursor-pointer font-semibold">外部模型设置与审计</summary>
    {error && <p role="alert" className="my-3 text-sm">{error}</p>}
    {settings && <div className="mt-4 space-y-4 text-sm">
      <button type="button" className="rounded border border-border px-3 py-2" disabled={busy}
        onClick={() => void save(!settings.enabled, settings.public_ids)}>
        {settings.enabled ? '关闭外部模型' : '开启外部模型'}
      </button>
      <span className="ml-3" role="status">{settings.enabled ? '已开启' : '已关闭'}</span>
      <fieldset className="space-y-2">
        <legend className="font-medium">已确认可对外公开的资料</legend>
        <p className="text-muted-foreground">仅标记已核实可对外公开的现行资料。标记影响问答资格，文件原文始终留在本地。</p>
        {settings.documents.length === 0 && <p>暂无符合条件的公开候选。</p>}
        {settings.documents.map(doc => <label key={doc.id} className="flex items-start gap-2">
          <input type="checkbox" checked={settings.public_ids.includes(doc.id)} disabled={busy}
            onChange={event => void save(settings.enabled, event.target.checked ? [...settings.public_ids, doc.id] :
              settings.public_ids.filter(id => id !== doc.id))} />{doc.name}
        </label>)}
      </fieldset>
      <form onSubmit={filter} className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
        <label className="grid gap-1">用户<input className="rounded border border-border px-2 py-1" value={username} onChange={event => setUsername(event.target.value)} /></label>
        <label className="grid gap-1">日期<input className="rounded border border-border px-2 py-1" type="date" value={date} onChange={event => setDate(event.target.value)} /></label>
        <button className="rounded border border-border px-3 py-1">查询外发审计</button>
      </form>
      {rows?.length === 0 && <p>没有符合条件的记录。</p>}
      {rows?.length ? <ul className="max-h-96 divide-y divide-border overflow-auto">{rows.map((row, index) => <li key={index} className="space-y-1 py-3 break-words">
        <p>{new Date(row.at * 1000).toLocaleString()} · {row.username} · {row.blocked ? '已拦截' : row.event==='dispatch'?'已提交发送':'请求失败'}</p>
        <p>{row.question}</p>
        {row.reason && <p>原因 {row.reason}</p>}
        {row.sent && <p>发送内容 {row.sent}</p>}
        {row.document_ids.length > 0 && <p className="text-xs text-muted-foreground">命中文档 {row.document_ids.join('、')}</p>}
      </li>)}</ul> : null}
    </div>}
  </details>
}

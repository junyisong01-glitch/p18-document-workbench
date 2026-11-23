import { Moon, Sun } from 'lucide-react'
import { setAppearance, useAppearance } from '@/lib/appearance'

export function AppearanceToggle() {
  const theme = useAppearance()
  const dark = theme === 'charcoal'
  const action = dark ? '切换为蓝白风格' : '切换为深色暖灰风格'
  return <button type="button" className="appearance-toggle" onClick={() => setAppearance(dark ? 'blue' : 'charcoal')} title={action} aria-label={action}>
    {dark ? <Moon size={15} aria-hidden="true"/> : <Sun size={15} aria-hidden="true"/>}
    <span>{dark ? '深色暖灰' : '蓝白风格'}</span>
  </button>
}

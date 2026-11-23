import { Check, ChevronDown, Palette } from 'lucide-react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { setAppearance, useAppearance } from '@/lib/appearance'

export function AppearanceToggle() {
  const theme = useAppearance()
  return <DropdownMenu.Root>
    <DropdownMenu.Trigger asChild>
      <button type="button" className="appearance-toggle" aria-label="切换风格">
        <Palette size={16} aria-hidden="true"/><span>切换风格</span><ChevronDown size={13} aria-hidden="true"/>
      </button>
    </DropdownMenu.Trigger>
    <DropdownMenu.Portal>
      <DropdownMenu.Content className="appearance-menu" align="end" sideOffset={8} collisionPadding={12}>
        <DropdownMenu.Label className="appearance-menu-label">选择界面风格</DropdownMenu.Label>
        <DropdownMenu.RadioGroup value={theme} onValueChange={value => { if(value === 'blue' || value === 'charcoal') setAppearance(value) }}>
          <DropdownMenu.RadioItem value="blue" className="appearance-option">
            <span className="appearance-swatch appearance-swatch-blue" aria-hidden="true"/>
            <span className="appearance-option-copy"><strong>蓝白风格</strong><small>清爽明亮 · 默认风格</small></span>
            <DropdownMenu.ItemIndicator className="appearance-check"><Check size={17}/><span className="sr-only">当前使用</span></DropdownMenu.ItemIndicator>
          </DropdownMenu.RadioItem>
          <DropdownMenu.RadioItem value="charcoal" className="appearance-option">
            <span className="appearance-swatch appearance-swatch-charcoal" aria-hidden="true"/>
            <span className="appearance-option-copy"><strong>深色暖灰</strong><small>深色导航 · 温暖柔和</small></span>
            <DropdownMenu.ItemIndicator className="appearance-check"><Check size={17}/><span className="sr-only">当前使用</span></DropdownMenu.ItemIndicator>
          </DropdownMenu.RadioItem>
        </DropdownMenu.RadioGroup>
      </DropdownMenu.Content>
    </DropdownMenu.Portal>
  </DropdownMenu.Root>
}

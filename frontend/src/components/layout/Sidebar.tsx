import { Box, Library, MessageSquare, Search, ShieldCheck, type LucideIcon } from 'lucide-react';

interface NavItem {
  label: string;
  icon: LucideIcon;
  active?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { label: '文档管理', icon: Library, active: true },
  { label: '知识检索', icon: Search },
  { label: '知识问答', icon: MessageSquare },
];

export default function Sidebar() {
  return (
    <aside className="sticky top-0 flex h-screen w-[232px] shrink-0 flex-col border-r border-line bg-white px-5 py-6">
      <div className="flex items-center gap-3 px-1">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-600 ring-1 ring-blue-100">
          <Box className="h-6 w-6" strokeWidth={1.75} />
        </div>
        <div>
          <p className="text-base font-semibold leading-[1.2] text-ink">P18 知识库</p>
          <p className="mt-0.5 text-xs leading-[1.5] text-ink-muted">研发文档检索原型</p>
        </div>
      </div>

      <nav className="mt-8 flex flex-col gap-1.5">
        {NAV_ITEMS.map(({ label, icon: Icon, active }) => (
          <button
            key={label}
            type="button"
            aria-current={active ? 'page' : undefined}
            onClick={() => { if (!active) location.assign(label === '知识检索' ? '/?view=search' : '/?view=rag'); }}
            className={`flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm transition ${
              active
                ? 'bg-blue-600 font-medium text-white shadow-[0_6px_16px_rgba(37,99,235,0.25)]'
                : 'text-ink-muted hover:bg-slate-50 hover:text-ink'
            }`}
          >
            <Icon className="h-[18px] w-[18px]" strokeWidth={1.75} />
            {label}
          </button>
        ))}
      </nav>

      <div className="mt-auto rounded-2xl border border-blue-100 bg-gradient-to-b from-blue-50 to-sky-50 p-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white text-blue-600 shadow-sm">
          <ShieldCheck className="h-5 w-5" strokeWidth={1.75} />
        </div>
        <p className="mt-3 text-sm font-semibold leading-[1.2] text-ink">本地处理</p>
        <p className="mt-1.5 text-xs leading-[1.5] text-ink-muted">
          资料先在本机检索；机密文档不会发送给外部模型。
        </p>
      </div>
    </aside>
  );
}

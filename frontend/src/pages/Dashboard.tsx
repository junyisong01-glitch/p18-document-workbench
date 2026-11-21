import { demoIdentityName } from '@/lib/demo-identity-names'
// 页面二：工作台
// 展示当前用户岗位、当前知识库、访问范围、知识库模式与有依据的统计，
// 并提供文档管理与知识问答入口。
import {BusinessDashboard} from '@/components/BusinessDashboard'
import { Link } from 'react-router'
import { ArrowRight, FileStack, MessageSquareText, ShieldCheck } from 'lucide-react'
import { useKnowledgeBase, useSession } from '@/lib/session'
import { KNOWLEDGE_BASES } from '@/lib/types'
import { PageHeader } from '@/components/bits'
import type { KbId } from '@/lib/types'

const ENTRIES = [
  {
    to: '/documents',
    icon: FileStack,
    title: '文档管理',
    en: 'Documents',
    desc: '按真实目录分类浏览有权限的文档，查看解析、切分、复核与索引状态，预览原文并下载。',
  },
  {
    to: '/qa',
    icon: MessageSquareText,
    title: '知识问答',
    en: 'Ask',
    desc: '在授权条件下人工选择证据并确认发送，获取带引用来源的参考回答。',
  },
] as const

export default function DashboardPage() {
  const { user, kbId, setKb, visibleDocs, searchableDocs, kbStats, availableKbs } = useSession()
  const kb = useKnowledgeBase()

  if(kbId==='business')return <BusinessDashboard/>
  return (
    <div className="space-y-10">
      <PageHeader
        kicker="Dashboard"
        title={demoIdentityName(user?.username) ?? user?.role.name ?? '工作台'}
        desc={`当前以「${user?.role.name}」岗位访问${kb.name}，可见文档 ${visibleDocs.length} 份，其中现行可检索 ${searchableDocs.length} 份。`}
        extra={
          <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-[12px] text-muted-foreground">
            <ShieldCheck className="size-4 text-[hsl(148_32%_32%)]" strokeWidth={1.8} />
            会话有效 · 岗位由服务端确定
          </div>
        }
      />

      {/* 价值主张 */}
      <section className="grid grid-cols-1 md:grid-cols-3 divide-x divide-border border border-border bg-card">
        {[
          ['找得到', '混合检索', '向量与关键词融合排序，默认 Top-5 直达来源片段。'],
          ['查得清', '证据可核', '检索结果附证据与原文预览，可人工核对来源。'],
          ['管得住', '权限可控', '按服务端岗位权限过滤范围，外发授权严格受控。'],
        ].map(([t, en, d]) => (
          <div key={t} className="px-6 py-5">
            <div className="font-mono2 text-[9px] font-medium uppercase tracking-[0.24em] text-muted-foreground">
              {en}
            </div>
            <div className="mt-2 font-display text-[18px] font-semibold tracking-tight">{t}</div>
            <p className="mt-1.5 text-[12px] leading-relaxed text-muted-foreground">{d}</p>
          </div>
        ))}
      </section>

      {/* 知识库与访问范围 */}
      <section>
        <div className="kicker mb-4">Knowledge Base & Access</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {(Object.keys(KNOWLEDGE_BASES) as KbId[]).filter(id=>availableKbs.includes(id)).map((id) => {
            const k = KNOWLEDGE_BASES[id]
            const active = id === kbId
            return (
              <button
                key={id}
                onClick={() => setKb(id)}
                className={`ease-junyi group border p-6 text-left transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)] ${
                  active
                    ? 'border-[hsl(12_74%_42%/0.55)] bg-card shadow-[0_1px_0_hsl(12_74%_42%/0.25)]'
                    : 'border-border bg-card/50 hover:border-muted-foreground/40 hover:bg-card'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2.5">
                      <span
                        className={`size-2 rounded-full ${
                          active ? 'bg-[hsl(12_74%_46%)]' : 'bg-muted-foreground/40'
                        }`}
                      />
                      <span className="font-display text-[17px] font-semibold tracking-tight">
                        {k.name}
                      </span>
                    </div>
                    <div className="mt-1.5 text-[12px] text-muted-foreground">{k.modeLabel}</div>
                  </div>
                  <span
                    className={`rounded-sm border px-2 py-0.5 font-mono2 text-[10px] uppercase tracking-[0.12em] ${
                      k.readonly
                        ? 'border-border bg-secondary text-muted-foreground'
                        : 'border-[hsl(148_32%_32%/0.45)] bg-[hsl(148_32%_32%/0.08)] text-[hsl(148_32%_28%)]'
                    }`}
                  >
                    {k.readonly?'只读':k.id==='business'?user?.accessRole==='guest'?'授权只读':'提交与审批流程':user?.admin?'可管理':'权限内只读'}
                  </span>
                </div>

                {kbStats[k.id] && (
                  <div className="mt-5 grid grid-cols-4 gap-3 border-t border-border pt-4">
                    {[
                      ['文档', kbStats[k.id].totalDocs],
                      ['DOCX', kbStats[k.id].docx],
                      ['XLSX', kbStats[k.id].xlsx],
                      ['已索引', kbStats[k.id].indexedDocs],
                    ].map(([label, v]) => (
                      <div key={label as string}>
                        <div className="font-mono2 text-[20px] font-semibold tracking-tight">
                          {typeof v==='number'&&v<0?'—':v}
                        </div>
                        <div className="mt-0.5 text-[10px] text-muted-foreground">{label}</div>
                      </div>
                    ))}
                  </div>
                )}
                <div className="mt-4 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>数据相互隔离，检索不跨库混合</span>
                  <span
                    className={`ease-junyi flex items-center gap-1 font-medium transition-colors duration-200 ${
                      active ? 'text-[hsl(12_74%_42%)]' : 'group-hover:text-foreground'
                    }`}
                  >
                    {active ? '当前知识库' : '切换到此库'}
                    <ArrowRight className="size-3" />
                  </span>
                </div>
              </button>
            )
          })}
        </div>
        <p className="mt-3 text-[11px] text-muted-foreground">
          统计来自当前登录身份的服务端数据；其他知识库切换后加载。
        </p>
      </section>

      {/* 功能入口 */}
      <section>
        <div className="kicker mb-4">Workspace</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {ENTRIES.map((e) => (
            <Link
              key={e.to}
              to={e.to}
              className="ease-junyi group border border-border bg-card p-6 transition-all duration-200 hover:-translate-y-0.5 hover:border-[hsl(12_74%_42%/0.5)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(12_74%_42%)]"
            >
              <e.icon
                className="size-5 text-muted-foreground transition-colors duration-200 group-hover:text-[hsl(12_74%_42%)]"
                strokeWidth={1.8}
              />
              <div className="mt-4 flex items-baseline gap-2">
                <span className="font-display text-[16px] font-semibold tracking-tight">
                  {e.title}
                </span>
                <span className="font-mono2 text-[9px] uppercase tracking-[0.2em] text-muted-foreground">
                  {e.en}
                </span>
              </div>
              <p className="mt-2 text-[12px] leading-relaxed text-muted-foreground">{e.desc}</p>
              <div className="mt-4 flex items-center gap-1.5 text-[12px] font-medium text-[hsl(12_74%_42%)]">
                进入
                <ArrowRight className="ease-junyi size-3.5 transition-transform duration-200 group-hover:translate-x-0.5" />
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  )
}

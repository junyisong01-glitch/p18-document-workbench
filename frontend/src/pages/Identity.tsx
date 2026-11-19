// 页面六：权限与身份
// 仅展示当前用户自己的身份与会话权限结果（只读）。
// 不显示全岗位权限表，不提供修改岗位或身份切换。
import { KeyRound, Lock, ShieldCheck } from 'lucide-react'
import { PageHeader } from '@/components/bits'
import { useKnowledgeBase, useSession } from '@/lib/session'

export default function IdentityPage() {
  const { user, visibleDocs, searchableDocs, archivedDocs } = useSession()
  const kb = useKnowledgeBase()

  if (!user) return null

  const rows: [string, React.ReactNode][] = [
    ['当前账号', <span className="font-mono2">{user.username}</span>],
    ['姓名', user.name],
    ['当前岗位', user.role.name],
    ['所属部门', user.role.dept],
    ['当前知识库', kb.name],
    [
      '可访问文档',
      <span>
        <span className="font-mono2 font-semibold">{visibleDocs.length}</span> 份
        {archivedDocs.length > 0 && (
          <span className="ml-2 text-[12px] text-muted-foreground">
            （含已废止归档 {archivedDocs.length} 份，仅供历史查看）
          </span>
        )}
      </span>,
    ],
    [
      '现行可检索文档',
      <span className="font-mono2 font-semibold">{searchableDocs.length}</span>,
    ],
    [
      '访问模式',
      kb.readonly ? (
        <span className="inline-flex items-center gap-1.5 text-[hsl(36_60%_32%)]">
          <Lock className="size-3.5" />
          只读 — 不可上传、编辑、删除或重新索引
        </span>
      ) : (
        kb.id==='business'?({boss:'全局读取、任免主管、公开与物理删除；可自审本人提交，可邀请新人',supervisor:'本部门提交、审核、发布与软删除；可自审，本部门普通旧资料可读；机密仍须授权',employee:'本部门提交、本人轻量勘误与上传新版本；无审批、公开或删除权',guest:'仅公开及单独获准资料；不能上传、审批或删除'}[user.accessRole||'employee']):user.admin?'演示库文档管理员；读取及外发仍须逐份许可':'演示库按原岗位只读；无上传、审批或删除权'
      ),
    ],
    [
      '外部 AI 使用',
      kb.externalAiAllowed
        ? '仅获逐份许可的资料可外发：需配置个人Key、人工选择、容量校验与发送前确认'
        : '受限：该知识库禁止向外部大模型发送资料',
    ],
  ]

  return (
    <div className="space-y-6">
      <PageHeader
        kicker="Identity & Access"
        title="权限与身份"
        desc="本页为你的登录会话与服务端权限结果的只读展示。岗位由账号决定，前端不可修改，也不提供身份切换。"
        extra={
          <span className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 text-[12px] text-muted-foreground">
            <ShieldCheck className="size-4 text-[hsl(148_32%_32%)]" strokeWidth={1.8} />
            会话有效
          </span>
        }
      />

      <div className="border border-border bg-card">
        {/* 身份摘要 */}
        <div className="flex items-center gap-5 border-b border-border px-7 py-6">
          <div className="flex size-14 items-center justify-center rounded-full border border-border bg-secondary font-display text-[20px] font-semibold">
            {user.name.slice(0, 1)}
          </div>
          <div>
            <div className="font-display text-[18px] font-semibold tracking-tight">
              {user.name}
            </div>
            <div className="mt-1 flex items-center gap-2 text-[12px] text-muted-foreground">
              <KeyRound className="size-3.5" strokeWidth={1.8} />
              {user.role.name} · {user.role.dept}
            </div>
          </div>
          <div className="ml-auto grid grid-cols-2 gap-8 border-l border-border pl-8">
            <div>
              <div className="font-mono2 text-[26px] font-semibold leading-none">
                {visibleDocs.length}
              </div>
              <div className="mt-1.5 text-[11px] text-muted-foreground">可访问文档</div>
            </div>
            <div>
              <div className="font-mono2 text-[26px] font-semibold leading-none">
                {searchableDocs.length}
              </div>
              <div className="mt-1.5 text-[11px] text-muted-foreground">现行可检索</div>
            </div>
          </div>
        </div>

        {/* 明细 */}
        <dl>
          {rows.map(([k, v], i) => (
            <div
              key={k}
              className={`grid grid-cols-[200px_minmax(0,1fr)] items-baseline gap-6 px-7 py-3.5 ${
                i % 2 === 0 ? 'bg-secondary/25' : ''
              }`}
            >
              <dt className="font-mono2 text-[11px] uppercase tracking-[0.14em] text-muted-foreground">
                {k}
              </dt>
              <dd className="text-[13px]">{v}</dd>
            </div>
          ))}
        </dl>
      </div>

      <p className="max-w-2xl border-l-2 border-border pl-4 text-[12px] leading-relaxed text-muted-foreground">
        文档可见范围由服务端按岗位权限实时判定；本页统计与列表仅覆盖你本人有权限的内容。未获接口支持的身份字段不予显示，不会以前端隐藏代替权限控制。
      </p>
    </div>
  )
}

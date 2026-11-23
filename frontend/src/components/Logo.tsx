// 均易品牌标识：以「信息连接的迹线」构成的 J/Y 字形。
// 设计理念 — 一条贯穿的迹线串联文档节点，终点落下一枚朱砂「迹点」，
// 呼应品牌标语「让每一份信息，都有迹可循」。

export function LogoMark({
  size = 32,
  className = '',
  ink = 'currentColor',
  trace = 'var(--brand-trace, #2468ec)',
}: {
  size?: number
  className?: string
  ink?: string
  trace?: string
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      className={className}
      role="img"
      aria-label="均易标识"
    >
      {/* J 形主干：横笔起，竖笔落，末端勾起 */}
      <path
        d="M10 12 H30 V30"
        stroke={ink}
        strokeWidth="3.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M30 30 C30 36 26 39 21 39 C17 39 14 37 13 34"
        stroke={ink}
        strokeWidth="3.5"
        strokeLinecap="round"
      />
      {/* Y 形迹线：自右上节点斜落，与主干交汇 */}
      <path
        d="M38 10 L30 21"
        stroke={ink}
        strokeWidth="3.5"
        strokeLinecap="round"
      />
      {/* 节点与迹点 */}
      <circle cx="10" cy="12" r="3.2" fill={ink} />
      <circle cx="38" cy="10" r="3.2" fill={ink} />
      <circle cx="13" cy="34" r="3.6" fill={trace} />
    </svg>
  )
}

export function LogoLockup({
  dark = false,
  compact = false,
}: {
  dark?: boolean
  compact?: boolean
}) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark size={compact ? 26 : 32} ink={dark ? '#EDE6D8' : 'var(--brand-trace, #2468ec)'} />
      <div className="leading-none">
        <div
          className={`font-display text-[17px] font-semibold tracking-wide ${
            dark ? 'text-[#EDE6D8]' : 'text-foreground'
          }`}
        >
          均易
        </div>
        {!compact && (
          <div
            className={`mt-1 font-mono2 text-[9px] font-medium uppercase tracking-[0.32em] ${
              dark ? 'text-[#8f8674]' : 'text-muted-foreground'
            }`}
          >
            JUNYI
          </div>
        )}
      </div>
    </div>
  )
}

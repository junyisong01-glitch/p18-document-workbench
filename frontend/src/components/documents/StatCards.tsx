import { AlertTriangle, CheckCircle2, Clock, FileText, Lock, type LucideIcon } from 'lucide-react';

export interface LibraryStats {
  viewable: number;
  processing: number;
  needsReview: number;
  searchable: number;
  confidential: number;
}

interface StatCardProps {
  label: string;
  value: number;
  icon: LucideIcon;
  tone: 'blue' | 'violet' | 'amber' | 'emerald' | 'red';
}

const TONE_CLASSES: Record<StatCardProps['tone'], string> = {
  blue: 'bg-blue-50 text-blue-600 ring-blue-100',
  violet: 'bg-violet-50 text-violet-600 ring-violet-100',
  amber: 'bg-amber-50 text-amber-600 ring-amber-100',
  emerald: 'bg-emerald-50 text-emerald-600 ring-emerald-100',
  red: 'bg-red-50 text-red-600 ring-red-100',
};

function StatCard({ label, value, icon: Icon, tone }: StatCardProps) {
  return (
    <div className="flex items-center gap-4 rounded-2xl border border-line bg-white p-5 shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-[0_14px_32px_rgba(37,99,235,0.1)]">
      <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ring-1 ${TONE_CLASSES[tone]}`}>
        <Icon className="h-6 w-6" strokeWidth={1.75} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-semibold leading-[1.2] tabular-nums text-ink">{value}</p>
        <p className="mt-1 truncate text-sm leading-[1.5] text-ink-muted">{label}</p>
      </div>
    </div>
  );
}

export default function StatCards({ stats }: { stats: LibraryStats }) {
  return (
    <div className="grid grid-cols-5 gap-4">
      <StatCard label="我可查看的文档" value={stats.viewable} icon={FileText} tone="blue" />
      <StatCard label="正在处理" value={stats.processing} icon={Clock} tone="violet" />
      <StatCard label="需要复核" value={stats.needsReview} icon={AlertTriangle} tone="amber" />
      <StatCard label="可检索资料" value={stats.searchable} icon={CheckCircle2} tone="emerald" />
      <StatCard label="机密文档（不外发）" value={stats.confidential} icon={Lock} tone="red" />
    </div>
  );
}

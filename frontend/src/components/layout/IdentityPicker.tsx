import {Check, ChevronDown} from 'lucide-react';
import {useEffect, useRef, useState} from 'react';
import {IDENTITIES} from '@/types/document';
import {api} from '@/lib/documentStore';

export default function IdentityPicker({identity}: {identity: string}) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const options = useRef<(HTMLButtonElement | null)[]>([]);
  const selected = Math.max(0, IDENTITIES.findIndex(i => i.label === identity));

  useEffect(() => {
    if (!open) return;
    options.current[selected]?.focus();
    const dismiss = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', dismiss);
    return () => document.removeEventListener('pointerdown', dismiss);
  }, [open, selected]);

  async function choose(next: string) {
    if (pending) return;
    if (next === identity) { setOpen(false); trigger.current?.focus(); return; }
    setPending(true);
    setError('');
    try {
      await api('/api/library/demo-session', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({identity: next})});
      sessionStorage.clear();
      location.replace('/library/');
    } catch (e) {
      setError((e as Error).message);
      setPending(false);
    }
  }

  return <div ref={root} className="relative">
    <button ref={trigger} type="button" aria-label={`演示身份：${identity}`} aria-haspopup="listbox" aria-expanded={open}
      onClick={() => setOpen(!open)} onKeyDown={e => {if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {e.preventDefault(); setOpen(true);}}}
      className="flex h-12 w-[210px] items-center justify-between rounded-2xl border border-blue-300 bg-white px-5 text-base font-semibold text-ink shadow-sm outline-none focus-visible:ring-4 focus-visible:ring-blue-100">
      {identity}<ChevronDown size={16}/>
    </button>
    {open && <div role="listbox" aria-label="演示身份" aria-busy={pending} className="identity-menu absolute right-0 top-0 z-[70] w-[258px] overflow-y-auto p-1.5"
      onKeyDown={e => {
        const index = options.current.indexOf(document.activeElement as HTMLButtonElement);
        if (e.key === 'Escape') {e.preventDefault(); setOpen(false); trigger.current?.focus();}
        if (e.key === 'Tab') setOpen(false);
        if (['ArrowDown','ArrowUp','Home','End'].includes(e.key)) {
          e.preventDefault();
          const next = e.key === 'Home' ? 0 : e.key === 'End' ? IDENTITIES.length-1 : (index + (e.key === 'ArrowDown' ? 1 : -1) + IDENTITIES.length) % IDENTITIES.length;
          options.current[next]?.focus();
        }
      }}>
      {IDENTITIES.map((item, index) => <button key={item.key} ref={el => {options.current[index] = el;}}
        type="button" role="option" aria-selected={identity === item.label} aria-disabled={pending} tabIndex={-1}
        onClick={() => void choose(item.label)} className="identity-option flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-base font-semibold outline-none">
        <span className="w-5 shrink-0">{identity === item.label && <Check size={20} strokeWidth={2.5}/>}</span>{item.label}
      </button>)}
    </div>}
    {error && <p role="alert" className="mt-2 max-w-[258px] text-sm text-red-600">{error}</p>}
  </div>;
}

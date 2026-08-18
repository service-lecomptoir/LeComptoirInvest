import { CheckCircle2, Info, XCircle, X } from 'lucide-react'
import clsx from 'clsx'
import { useToastStore } from '@/store/toast'

export function Toasts() {
  const { toasts, dismiss } = useToastStore()
  if (!toasts.length) return null
  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 w-[min(24rem,calc(100vw-2rem))]">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={clsx(
            'flex items-start gap-2.5 rounded-xl border px-3.5 py-3 shadow-lg bg-white',
            t.kind === 'error' && 'border-red-200',
            t.kind === 'success' && 'border-emerald-200',
            t.kind === 'info' && 'border-sky-200',
          )}
        >
          {t.kind === 'success' && <CheckCircle2 size={17} className="mt-0.5 shrink-0 text-emerald-600" />}
          {t.kind === 'error' && <XCircle size={17} className="mt-0.5 shrink-0 text-red-600" />}
          {t.kind === 'info' && <Info size={17} className="mt-0.5 shrink-0 text-sky-600" />}
          <p className="text-sm text-gray-800 leading-snug flex-1">{t.message}</p>
          <button onClick={() => dismiss(t.id)} className="text-gray-400 hover:text-gray-600 shrink-0">
            <X size={15} />
          </button>
        </div>
      ))}
    </div>
  )
}

import { forwardRef, useEffect, useId, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { InfoBubble } from '@/components/common/InfoBubble'
import { Button, Select, inputBaseClass } from '@/components/ui'

/**
 * What `PlanChangeOffer` borrows from THIS product: its window, its
 * fields, its ⓘ bubble and its buttons (its words and its server: `planOfferHost.ts`).
 * `PlanChangeOffer.tsx` and `planOffer.ts` are the
 * same files in every product (the owner, 12 Oct 2026); this one is the product's own.
 */

/**
 * A window of the house (this product has no shared one): Escape closes it, a click beside
 * it does not (a stray click is not an answer).
 */
export function PlanDialog({ title, onCancel, children }: { title: string; onCancel: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onCancel])
  return createPortal(
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 px-4" role="dialog" aria-modal="true" aria-label={title}>
      <div className="max-h-[90dvh] w-full max-w-md space-y-3 overflow-y-auto rounded-xl bg-white p-5 shadow-lg">
        <p className="text-base font-semibold text-gray-900">{title}</p>
        {children}
      </div>
    </div>,
    document.body,
  )
}

export function PlanSelect({
  label,
  hint,
  value,
  onChange,
  options,
}: {
  label: string
  hint: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-gray-700">
        {label}
      </label>
      <Select id={id} className={inputBaseClass} value={value} onChange={onChange} options={options} />
      <p className="mt-1 text-xs text-gray-500">{hint}</p>
    </div>
  )
}

export function PlanTextarea({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint: string
  value: string
  onChange: (value: string) => void
}) {
  const id = useId()
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-gray-700">
        {label}
      </label>
      <textarea
        id={id}
        rows={3}
        maxLength={2000}
        className={inputBaseClass}
        value={value}
        onChange={event => onChange(event.target.value)}
      />
      <p className="mt-1 text-xs text-gray-500">{hint}</p>
    </div>
  )
}

/** The ⓘ bubble of the house: the detail on demand, never a sentence under a figure. */
export function PlanBubble({ label, text }: { label: string; text: string }) {
  return <InfoBubble label={label} text={text} />
}

export const PlanButton = forwardRef<
  HTMLButtonElement,
  { tone?: 'quiet' | 'primary'; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>
>(function PlanButton({ tone = 'quiet', children, ...rest }, ref) {
  return (
    <Button ref={ref} type="button" size="sm" variant={tone === 'primary' ? 'primary' : 'secondary'} {...rest}>
      {children}
    </Button>
  )
})

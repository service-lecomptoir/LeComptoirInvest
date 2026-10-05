import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TermsKind, TermsText } from '@/api/terms'
import { numericDay } from '@/lib/format'
import { asked, type TermsBox, type Ticked } from '@/lib/terms'
import { TermsReader } from './TermsReader'

/** One required box, unticked, its reader one tap away, its help under it. */
export function TermsCheckbox({
  text,
  checked,
  onChange,
  label,
  hint,
}: {
  text: TermsText
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  hint: string
}) {
  const { t } = useTranslation()
  const id = useId()
  const [reading, setReading] = useState(false)
  return (
    <div>
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <label htmlFor={id} className="flex items-start gap-2 text-sm text-gray-800 cursor-pointer">
          <input
            id={id}
            type="checkbox"
            checked={checked}
            onChange={(event) => onChange(event.target.checked)}
            className="mt-0.5 h-4 w-4 shrink-0 accent-brand-navy"
          />
          <span>
            {label}
            <span className="text-red-500"> *</span>
          </span>
        </label>
        <button
          type="button"
          onClick={() => setReading(true)}
          className="text-sm text-brand-navy underline hover:no-underline"
        >
          {t('terms.read')}
        </button>
      </div>
      <p className="mt-1 ml-6 text-xs text-gray-500">{hint}</p>
      {reading && <TermsReader text={text} onClose={() => setReading(false)} />}
    </div>
  )
}

/**
 * The sign-up's boxes: the terms of use always, the terms of sale with a catalogue plan,
 * each only when Alice publishes it.
 */
export function TermsBoxes({
  boxes,
  withSale,
  ticked,
  onTick,
}: {
  boxes: Record<TermsKind, TermsBox>
  withSale: boolean
  ticked: Ticked
  onTick: (kind: TermsKind, checked: boolean) => void
}) {
  const { t } = useTranslation()
  const kinds = asked(withSale)
  if (kinds.some((kind) => boxes[kind].state === 'unavailable')) {
    return (
      <p role="alert" className="text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
        {t('terms.signup.unavailable')}
      </p>
    )
  }
  const shown = kinds.flatMap((kind) => {
    const box = boxes[kind]
    return box.state === 'ready' ? [{ kind, text: box.text }] : []
  })
  if (!shown.length) return null
  return (
    <div className="space-y-3">
      {shown.map(({ kind, text }) => (
        <TermsCheckbox
          key={kind}
          text={text}
          checked={ticked[kind]}
          onChange={(checked) => onTick(kind, checked)}
          label={t(kind === 'cgu' ? 'terms.signup.acceptCgu' : 'terms.signup.acceptCgv')}
          hint={t('terms.signup.hint', {
            version: text.version,
            date: numericDay(text.effective_from),
          })}
        />
      ))}
    </div>
  )
}

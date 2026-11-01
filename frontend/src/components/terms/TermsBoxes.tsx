import { useEffect, useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TermsKind, TermsText } from '@/api/terms'
import { numericDay } from '@/lib/format'
import { asked, boxIsRead, type TermsBox, type Ticked } from '@/lib/terms'
import { TermsReader } from './TermsReader'

/**
 * One required box, unticked, its reader one tap away, its help under it.
 *
 * 🔴 `mustRead`: READ TO THE END FIRST (the terms of sale and the data processing
 * agreement, the owner, 1 Nov 2026). The box waits until the reader has reached the end of
 * the text, and « J'accepte » in the reader, enabled at the end only, ticks it. What was
 * read is the text itself (`boxIsRead`: `readText === text`), never a flag an effect
 * resets: a new text (a new version) asks again, and a box locked again is unticked.
 */
export function TermsCheckbox({
  text,
  checked,
  onChange,
  label,
  hint,
  mustRead = false,
}: {
  text: TermsText
  checked: boolean
  onChange: (checked: boolean) => void
  label: string
  hint: string
  /** The box cannot be ticked before the text is read to its end in the reader. */
  mustRead?: boolean
}) {
  const { t } = useTranslation()
  const id = useId()
  const [reading, setReading] = useState(false)
  const [readText, setReadText] = useState<TermsText | null>(null)
  const read = boxIsRead(mustRead, text, readText)
  // A box locked again (a new version came) is unticked: what was ticked was another text.
  useEffect(() => {
    if (!read && checked) onChange(false)
  }, [read, checked, onChange])
  return (
    <div>
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <label
          htmlFor={id}
          className={`flex items-start gap-2 text-sm text-gray-800 ${read ? 'cursor-pointer' : 'cursor-not-allowed'}`}
        >
          <input
            id={id}
            type="checkbox"
            checked={read && checked}
            disabled={!read}
            onChange={(event) => onChange(event.target.checked)}
            aria-describedby={`${id}-help`}
            className="mt-0.5 h-4 w-4 shrink-0 accent-brand-navy disabled:opacity-50"
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
          {t(text.kind === 'dpa' ? 'terms.readDpa' : 'terms.read')}
        </button>
      </div>
      <p id={`${id}-help`} className="mt-1 ml-6 text-xs text-gray-500">{hint}</p>
      {!read && <p className="mt-0.5 ml-6 text-xs text-gray-500">{t('terms.readToTick')}</p>}
      {reading && (
        <TermsReader
          text={text}
          onClose={() => setReading(false)}
          {...(mustRead
            ? {
                onReadToEnd: () => setReadText(text),
                read,
                onAccept: () => {
                  onChange(true)
                  setReading(false)
                },
              }
            : {})}
        />
      )}
    </div>
  )
}

/** The box's sentence, document by document. */
const ACCEPT_LABEL: Record<TermsKind, string> = {
  cgu: 'terms.signup.acceptCgu',
  cgv: 'terms.signup.acceptCgv',
  dpa: 'terms.signup.acceptDpa',
}

/**
 * The sign-up's boxes: the terms of use always, the terms of sale and the data processing
 * agreement with a catalogue plan, each only when Alice publishes it.
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
          mustRead={kind !== 'cgu'}
          label={t(ACCEPT_LABEL[kind])}
          hint={t('terms.signup.hint', {
            version: text.version,
            date: numericDay(text.effective_from),
          })}
        />
      ))}
    </div>
  )
}

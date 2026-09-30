import { useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'

/**
 * What a form checks before it sends, said UNDER EACH FIELD in the page's own words.
 *
 * 🔴 NEVER THE BROWSER'S BUBBLE. `required`, `min` and `type="email"` make the browser stop
 * the submission with a native dialog, in the browser's language rather than the page's
 * (« Veuillez allonger ce texte » on the page where a new customer chooses their password,
 * customer recipe of 30 Sept 2026), gone as soon as one taps elsewhere. Every form carries
 * `noValidate` and passes its fields through here; the message stays under the field until
 * the next attempt. Guard: `i18n/ui-rules.test.ts`.
 */
export interface Rule {
  /** The key the message is filed under: the field's `error={errors.<name>}`. */
  name: string
  value: string | null | undefined
  /** The field's label, for a summary over a long form. */
  label?: string
  required?: boolean
  /** An amount: a number, zero or more, two decimals at most (the `min="0"` and
   *  `step="0.01"` of the box, which the browser no longer enforces). */
  amount?: boolean
  email?: boolean
  minLength?: number
}

export type FieldErrors = Record<string, string>

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

function isAmount(raw: string): boolean {
  const n = Number(raw.replace(',', '.'))
  return Number.isFinite(n) && n >= 0 && Math.abs(n * 100 - Math.round(n * 100)) < 1e-6
}

/** The first thing wrong with each field, or nothing. Pure, so it is tested alone. */
export function fieldErrors(rules: Rule[], t: TFunction): FieldErrors {
  const errors: FieldErrors = {}
  for (const rule of rules) {
    const value = (rule.value ?? '').trim()
    if (!value) {
      if (rule.required) errors[rule.name] = t('form.required')
      continue
    }
    if (rule.amount && !isAmount(value)) errors[rule.name] = t('form.amount')
    else if (rule.email && !EMAIL.test(value)) errors[rule.name] = t('form.email')
    else if (rule.minLength && value.length < rule.minLength) {
      errors[rule.name] = t('form.minLength', { count: rule.minLength })
    }
  }
  return errors
}

/** The labels of the fields in error, in the order of the form, for a summary. */
export function labelsInError(rules: Rule[], errors: FieldErrors): string[] {
  return rules.filter((rule) => errors[rule.name] && rule.label).map((rule) => rule.label!)
}

/** A form's checks and the messages they left, until the next attempt. */
export function useFieldCheck() {
  const { t } = useTranslation()
  const [errors, setErrors] = useState<FieldErrors>({})
  const check = useCallback(
    (rules: Rule[]): boolean => {
      const found = fieldErrors(rules, t)
      setErrors(found)
      return Object.keys(found).length === 0
    },
    [t],
  )
  /** A message the form decides itself (two passwords that differ), under one field. */
  const flag = useCallback((name: string, message: string) => setErrors({ [name]: message }), [])
  return { errors, check, flag }
}

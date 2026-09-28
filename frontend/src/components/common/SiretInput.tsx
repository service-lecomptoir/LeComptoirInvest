import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { checkSirenSiret, cleanSiren, groupSiren, lookupSirenSiret, type SirenLookup } from '@/lib/siret'

interface Props {
  value: string
  onChange: (v: string) => void
  /** Called once the register answers, with everything it said: the parent fills what is empty. */
  onResolved?: (found: SirenLookup) => void
  className?: string
  id?: string
}

type State =
  | { kind: 'idle' }
  /** Ten to thirteen digits: a SIRET being typed, or a number with a digit missing. */
  | { kind: 'short'; digits: number }
  | { kind: 'invalid' }
  | { kind: 'checking' }
  | { kind: 'found'; name?: string }
  | { kind: 'not_found' }
  | { kind: 'error' }

/**
 * Company-number field with verification, for France only: the Luhn key (instantly), then
 * the register, which also brings back the name and the address for the form to fill. It
 * NEVER blocks entry: a number not found, or a silent register, only shows a warning.
 *
 * Same behaviour as Le Comptoir RH's `SiretInput`, the reference.
 */
export function SiretInput({ value, onChange, onResolved, className, id }: Props) {
  const { t } = useTranslation()
  const [state, setState] = useState<State>({ kind: 'idle' })
  const lastResolved = useRef<string>('')

  useEffect(() => {
    const d = cleanSiren(value)
    if (d.length !== 9 && d.length !== 14) {
      // Nothing is said while the first nine digits are typed; past nine, a number that
      // is not fourteen is said so.
      setState(d.length > 9 ? { kind: 'short', digits: d.length } : { kind: 'idle' })
      return
    }
    if (!checkSirenSiret(d).ok) {
      setState({ kind: 'invalid' })
      return
    }
    setState({ kind: 'checking' })
    const ctrl = new AbortController()
    const timer = setTimeout(async () => {
      const found = await lookupSirenSiret(d, ctrl.signal)
      if (ctrl.signal.aborted) return
      if (found.status === 'found') {
        setState({ kind: 'found', name: found.name })
        if (onResolved && lastResolved.current !== d) {
          lastResolved.current = d
          onResolved(found)
        }
      } else if (found.status === 'not_found') {
        setState({ kind: 'not_found' })
      } else {
        setState({ kind: 'error' })
      }
    }, 500)
    return () => {
      clearTimeout(timer)
      ctrl.abort()
    }
    // onResolved deliberately left out: a stable callback on the parent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  return (
    <div>
      {/* Digits only, fourteen at most, shown by groups (« 552 032 534 00703 ») and
          stored bare: the form and the server see the digits, the reader sees the groups. */}
      <input
        id={id}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        required
        className={className}
        value={groupSiren(value)}
        onChange={(e) => onChange(cleanSiren(e.target.value))}
      />
      {state.kind === 'short' && (
        <p className="mt-1 text-xs text-amber-700">{t('siretInput.short', { count: state.digits })}</p>
      )}
      {state.kind === 'invalid' && <p className="mt-1 text-xs text-amber-700">{t('siretInput.invalid')}</p>}
      {state.kind === 'checking' && <p className="mt-1 text-xs text-gray-500">{t('siretInput.checking')}</p>}
      {state.kind === 'found' && (
        <p className="mt-1 text-xs text-emerald-700">
          {state.name ? t('siretInput.verifiedAs', { name: state.name }) : t('siretInput.verified')}
        </p>
      )}
      {state.kind === 'not_found' && <p className="mt-1 text-xs text-amber-700">{t('siretInput.notFound')}</p>}
      {state.kind === 'error' && <p className="mt-1 text-xs text-gray-500">{t('siretInput.unreachable')}</p>}
    </div>
  )
}

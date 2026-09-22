import { forwardRef, useId, useState } from 'react'
import type { InputHTMLAttributes, ReactNode } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import clsx from 'clsx'

/** Base class shared by the input fields (input, select, textarea). */
export const inputBaseClass =
  'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500'

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode
  /** Error message: turns the border red and shows it under the field. */
  error?: string
  /** Help text shown under the field (ignored when `error` is set). */
  hint?: string
  required?: boolean
  /** Decorative content on the left (an icon). */
  leftIcon?: ReactNode
  containerClassName?: string
  /** Adds the eye that reveals the content. Reserved for password fields.
   *
   *  ⚠️ WHY IN THE PRIMITIVE AND NOT ON A SCREEN. The product holds four password fields
   *  (sign-in, and the three of the change). Putting the eye on one of them leaves the
   *  others without, and it is always the forgotten one that serves the day somebody types
   *  a long password on the keyboard of a telephone.
   *
   *  ⚠️ THE STATE ALWAYS STARTS FROM « MASQUE » and is never memorised: a field that
   *  reopens revealed because it had been revealed the day before shows a password to
   *  whoever walks behind the screen. */
  revealable?: boolean
}

/**
 * Unified text field. react-hook-form compatible: the ref is forwarded and
 * `{...register('x')}` can be spread straight in. With no `label` it renders a plain
 * styled <input> (parity with the former `className={inp}`).
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, required, leftIcon, className, containerClassName, id, revealable, type, ...rest },
  ref,
) {
  const { t } = useTranslation()
  const autoId = useId()
  const inputId = id ?? autoId
  const [revealed, setRevealed] = useState(false)
  const showEye = revealable && type === 'password'
  const field = (
    <div className={clsx((leftIcon || showEye) && 'relative')}>
      {leftIcon && (
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none">{leftIcon}</span>
      )}
      <input
        ref={ref}
        id={inputId}
        type={showEye && revealed ? 'text' : type}
        className={clsx(
          inputBaseClass,
          leftIcon && 'pl-9',
          showEye && 'pr-10',
          error && 'border-red-500 focus:ring-red-500',
          className,
        )}
        aria-invalid={!!error}
        {...rest}
      />
      {showEye && (
        <button
          type="button"
          // ⚠️ `tabIndex={-1}`: the tab key must lead from the password to the button that
          // submits, not to a display button. One reaches it with the mouse, or by
          // coming back.
          tabIndex={-1}
          onClick={() => setRevealed((v) => !v)}
          aria-pressed={revealed}
          aria-label={revealed ? t('password.hide') : t('password.reveal')}
          title={revealed ? t('password.hide') : t('password.reveal')}
          className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-700 rounded"
        >
          {revealed ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      )}
    </div>
  )

  if (!label && !error && !hint) return field

  return (
    <div className={containerClassName}>
      {label && (
        <label htmlFor={inputId} className="block text-sm font-medium text-gray-700 mb-1">
          {label}{required && <span className="text-red-500"> *</span>}
        </label>
      )}
      {field}
      {error ? (
        <p className="mt-1 text-xs text-red-600">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-gray-500">{hint}</p>
      ) : null}
    </div>
  )
})

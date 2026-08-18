import { forwardRef, useId } from 'react'
import type { InputHTMLAttributes, ReactNode } from 'react'
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
}

/**
 * Unified text field. react-hook-form compatible: the ref is forwarded and
 * `{...register('x')}` can be spread straight in. With no `label` it renders a plain
 * styled <input> (parity with the former `className={inp}`).
 */
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, required, leftIcon, className, containerClassName, id, ...rest },
  ref,
) {
  const autoId = useId()
  const inputId = id ?? autoId
  const field = (
    <div className={clsx(leftIcon && 'relative')}>
      {leftIcon && (
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none">{leftIcon}</span>
      )}
      <input
        ref={ref}
        id={inputId}
        className={clsx(
          inputBaseClass,
          leftIcon && 'pl-9',
          error && 'border-red-500 focus:ring-red-500',
          className,
        )}
        aria-invalid={!!error}
        {...rest}
      />
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

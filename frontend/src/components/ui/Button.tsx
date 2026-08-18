import { forwardRef } from 'react'
import type { ButtonHTMLAttributes, ReactNode } from 'react'
import clsx from 'clsx'
import { Spinner } from './Spinner'

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'success' | 'ghost'
export type ButtonSize = 'sm' | 'md' | 'lg'

const base =
  'inline-flex items-center justify-center gap-2 font-medium rounded-lg transition-colors focus:outline-none focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed'

const variantCls: Record<ButtonVariant, string> = {
  primary:   'bg-brand-navy text-white hover:bg-brand-navy-light focus:ring-brand-navy',
  secondary: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 focus:ring-brand-navy',
  danger:    'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
  success:   'bg-green-600 text-white hover:bg-green-700 focus:ring-green-500',
  ghost:     'text-gray-700 hover:bg-gray-100 focus:ring-gray-300',
}

const sizeCls: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-5 py-2.5 text-base',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  isLoading?: boolean
  leftIcon?: ReactNode
  rightIcon?: ReactNode
  fullWidth?: boolean
}

/**
 * The application's unified button.
 * Important: `type` is NOT forced to "button". The native behaviour is kept (a button
 * inside a <form> with no explicit type stays a submit), which guarantees parity
 * while the existing forms are migrated.
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', isLoading = false, leftIcon, rightIcon, fullWidth, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || isLoading}
      className={clsx(base, variantCls[variant], sizeCls[size], fullWidth && 'w-full', className)}
      {...rest}
    >
      {isLoading ? <Spinner size={size === 'sm' ? 14 : 16} /> : leftIcon}
      {children}
      {!isLoading && rightIcon}
    </button>
  )
})

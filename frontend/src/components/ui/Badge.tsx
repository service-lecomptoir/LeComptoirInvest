import type { ReactNode } from 'react'
import clsx from 'clsx'

export type BadgeVariant = 'green' | 'red' | 'yellow' | 'blue' | 'gray' | 'purple' | 'orange'

const variantCls: Record<BadgeVariant, string> = {
  green:  'bg-green-100 text-green-800',
  red:    'bg-red-100 text-red-800',
  yellow: 'bg-yellow-100 text-yellow-800',
  blue:   'bg-blue-100 text-blue-800',
  gray:   'bg-gray-100 text-gray-700',
  purple: 'bg-purple-100 text-purple-800',
  orange: 'bg-orange-100 text-orange-800',
}

const dotCls: Record<BadgeVariant, string> = {
  green:  'bg-green-500',
  red:    'bg-red-500',
  yellow: 'bg-yellow-500',
  blue:   'bg-blue-500',
  gray:   'bg-gray-400',
  purple: 'bg-purple-500',
  orange: 'bg-orange-500',
}

export interface BadgeProps {
  variant?: BadgeVariant
  /** Coloured dot to the left of the text. */
  dot?: boolean
  children: ReactNode
  className?: string
}

/** A coloured tag (status, counter, short label). Accepts an icon or any content
 *  through `children`, unlike StatusBadge (which takes a label only). */
export function Badge({ variant = 'gray', dot = false, children, className }: BadgeProps) {
  return (
    <span className={clsx('inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium', variantCls[variant], className)}>
      {dot && <span className={clsx('w-1.5 h-1.5 rounded-full', dotCls[variant])} />}
      {children}
    </span>
  )
}

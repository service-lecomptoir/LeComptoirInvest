import clsx from 'clsx'

interface SpinnerProps {
  /** Diameter in pixels (16 by default). */
  size?: number
  className?: string
}

/** Circular loading indicator. Inherits the text colour (`border-current`) so it
 *  fits its context (a filled button, a link, and so on). */
export function Spinner({ size = 16, className }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-label="Chargement"
      className={clsx('inline-block animate-spin rounded-full border-2 border-current border-t-transparent align-[-2px]', className)}
      style={{ width: size, height: size }}
    />
  )
}

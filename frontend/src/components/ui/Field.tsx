import type { ReactNode } from 'react'

/**
 * A label, the control it names, and the help UNDER it.
 *
 * 🔴 THE HELP GOES UNDER EACH FIELD, short, one per field (the house rule): a help written
 * once at the top of a form is read once and forgotten by the third box. `Input` carries its
 * own; this wraps everything else (a `Select`, a textarea, a lookup box).
 */
export function Field({
  label, htmlFor, hint, required, children,
}: {
  label: ReactNode
  htmlFor?: string
  hint?: ReactNode
  required?: boolean
  children: ReactNode
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-gray-700 mb-1">
        {label}{required && <span className="text-red-500"> *</span>}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>}
    </div>
  )
}

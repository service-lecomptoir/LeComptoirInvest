import type { ReactNode } from 'react'

/**
 * A label, the control it names, and the help UNDER it.
 *
 * 🔴 THE HELP GOES UNDER EACH FIELD, short, one per field (the house rule): a help written
 * once at the top of a form is read once and forgotten by the third box. `Input` carries its
 * own; this wraps everything else (a `Select`, a textarea, a lookup box).
 */
export function Field({
  label, htmlFor, hint, error, required, children,
}: {
  label: ReactNode
  htmlFor?: string
  hint?: ReactNode
  /** What the form's check found wrong: shown in red in place of the help. */
  error?: string
  required?: boolean
  children: ReactNode
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-gray-700 mb-1">
        {label}{required && <span className="text-red-500"> *</span>}
      </label>
      {/* The control it wraps is someone else's (a Select, a lookup box): its border turns
          red from here, as an Input's does on its own. */}
      <div className={error ? '[&_input]:border-red-500 [&_textarea]:border-red-500 [&_button]:border-red-500' : undefined}>
        {children}
      </div>
      {error ? (
        <p className="mt-1 text-xs text-red-600">{error}</p>
      ) : (
        hint && <p className="mt-1 text-xs text-gray-500">{hint}</p>
      )}
    </div>
  )
}

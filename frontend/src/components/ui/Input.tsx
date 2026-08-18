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
  /** Ajoute l'oeil qui devoile le contenu. Reserve aux champs de mot de passe.
   *
   *  ⚠️ POURQUOI DANS LA PRIMITIVE ET PAS SUR UN ECRAN. Le produit compte quatre champs de
   *  mot de passe (connexion, et les trois du changement). Poser l'oeil sur l'un d'eux
   *  laisse les autres sans, et c'est toujours celui qu'on a oublie qui sert le jour ou
   *  quelqu'un tape un mot de passe long au clavier d'un telephone.
   *
   *  ⚠️ L'ETAT PART TOUJOURS DE « MASQUE » et n'est jamais memorise : un champ qui se
   *  rouvre devoile parce qu'on l'avait devoile la veille montre un mot de passe a qui
   *  passe derriere l'ecran. */
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
          // ⚠️ `tabIndex={-1}` : la tabulation doit mener du mot de passe au bouton qui
          // valide, pas a un bouton d'affichage. On l'atteint a la souris, ou en revenant.
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

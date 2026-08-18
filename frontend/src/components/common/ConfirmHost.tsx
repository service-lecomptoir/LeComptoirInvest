import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui'
import { useConfirmStore } from '@/store/confirm'

/**
 * La fenêtre de confirmation du produit. Montée une fois, au-dessus de tout.
 *
 * ⚠️ ELLE NE SE FERME PAS SUR UN CLIC À CÔTÉ, et c'est une règle de la maison. Le clic hors
 * cadre est le geste qu'on fait sans y penser : le traiter comme un « non » est acceptable,
 * le traiter comme une réponse tout court ne l'est pas, parce que la personne n'a pas
 * répondu. Elle se ferme par « Annuler », par la croix, ou par Échap, qui sont trois gestes
 * délibérés.
 *
 * ⚠️ LE FOCUS PART SUR « ANNULER », jamais sur le bouton qui agit. Une fenêtre qui apparaît
 * sous un doigt déjà en train d'appuyer sur Entrée ne doit pas détruire quoi que ce soit.
 */
export function ConfirmHost() {
  const { t } = useTranslation()
  const request = useConfirmStore((s) => s.request)
  const answer = useConfirmStore((s) => s.answer)
  const cancelRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!request) return
    cancelRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') answer(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [request, answer])

  if (!request) return null

  return (
    <div
      className="fixed inset-0 z-[90] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-title"
    >
      {/* Le voile n'a PAS de gestionnaire de clic : voir le commentaire ci-dessus. */}
      <div className="absolute inset-0 bg-gray-900/40" />

      <div className="relative w-full max-w-md rounded-xl bg-white border border-gray-200 shadow-xl">
        <div className="px-5 pt-5 pb-4">
          <h2 id="confirm-title" className="text-base font-semibold text-gray-900">
            {request.title}
          </h2>
          {request.message && (
            <p className="mt-2 text-sm text-gray-600 leading-relaxed">{request.message}</p>
          )}
        </div>
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-gray-200 bg-gray-50 rounded-b-xl">
          <Button ref={cancelRef} variant="secondary" onClick={() => answer(false)}>
            {request.cancelLabel ?? t('common.cancel')}
          </Button>
          <Button
            variant={request.danger ? 'danger' : 'primary'}
            onClick={() => answer(true)}
          >
            {request.confirmLabel ?? t('common.confirm')}
          </Button>
        </div>
      </div>
    </div>
  )
}

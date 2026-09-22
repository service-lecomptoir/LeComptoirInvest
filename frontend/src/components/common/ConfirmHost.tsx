import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui'
import { useConfirmStore } from '@/store/confirm'

/**
 * The confirmation window of the product. Mounted once, above everything.
 *
 * ⚠️ IT DOES NOT CLOSE ON A CLICK BESIDE IT, and that is a rule of the house. The click
 * outside the frame is the gesture one makes without thinking: treating it as a « non » is
 * acceptable, treating it as an answer at all is not, because the person has not answered.
 * It closes through « Annuler », through the cross, or through Escape, which are three
 * deliberate gestures.
 *
 * ⚠️ THE FOCUS GOES TO « ANNULER », never to the button that acts. A window that appears
 * under a finger already pressing Enter must not destroy anything.
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
      {/* The veil has NO click handler: see the comment above. */}
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

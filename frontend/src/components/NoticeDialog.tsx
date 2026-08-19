import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Mail, Send, X } from 'lucide-react'
import { noticeApi } from '@/api'
import { errorMessage } from '@/api/client'
import { Button } from '@/components/ui'
import { Loading, Notice } from '@/components/common/Primitives'
import { toast } from '@/store/toast'
import type { CallNotice } from '@/types'

/**
 * The letter the fund is about to send, shown before it is sent.
 *
 * 🔴 IT IS IN THE INVESTOR'S LANGUAGE, NOT THE READER'S, and the dialog says which one.
 * A French manager previewing a notice to a British investor sees English text, and without
 * the label that reads as a bug. With it, it reads as the product doing the one thing that
 * matters here: writing to somebody in the language they chose.
 *
 * ⚠️ OPENING IT SENDS NOTHING. Reading and sending are two endpoints for exactly that
 * reason: a screen that marked the call as notified when it rendered would silence the
 * chasing list for anybody who merely looked, and the investor would still have received
 * nothing.
 */
export function NoticeDialog({
  callId,
  asOf,
  onClose,
  onSent,
}: {
  callId: string
  asOf: string
  onClose: () => void
  onSent?: () => void
}) {
  const { t } = useTranslation()
  const [notice, setNotice] = useState<CallNotice | null>(null)
  const [refused, setRefused] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    setNotice(null)
    setRefused(null)
    noticeApi
      .preview(callId, asOf)
      .then((r) => setNotice(r.data))
      // The server's sentence says WHICH letter cannot be written and why - never sent, a
      // settled call, not due yet. A generic failure would send the manager hunting.
      .catch((e) => setRefused(errorMessage(e)))
  }, [callId, asOf])

  const send = async () => {
    setSending(true)
    try {
      const r = await noticeApi.send(callId, asOf)
      setNotice(r.data)
      toast.success(t('notice.sent', { to: r.data.to ?? '' }))
      onSent?.()
    } catch {
      /* the interceptor showed the relay's own refusal */
    } finally {
      setSending(false)
    }
  }

  return (
    // ⚠️ NO CLOSE ON BACKDROP CLICK: this holds a letter about to go out to somebody, and a
    // stray click outside must not throw the manager's reading away.
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/40 p-4">
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <Mail size={16} className="text-brand-navy" />
            <h2 className="text-[15px] font-semibold text-gray-900">
              {t('notice.title')}
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label={t('common.close')}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-5 py-4 max-h-[60vh] overflow-y-auto">
          {refused ? (
            <Notice tone="warn" title={t('notice.cannotWrite')}>
              {refused}
            </Notice>
          ) : !notice ? (
            <Loading label={t('common.loading')} />
          ) : (
            <>
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm mb-4">
                <p className="text-gray-600">
                  {t('notice.to')}{' '}
                  <span className="font-medium text-gray-900">
                    {notice.to ?? t('notice.noAddress')}
                  </span>
                </p>
                <p className="text-gray-600">
                  {t('notice.language')}{' '}
                  <span className="font-medium text-gray-900 uppercase">
                    {notice.language}
                  </span>
                </p>
                <p className="text-gray-600">
                  {t('notice.kind')}{' '}
                  <span className="font-medium text-gray-900">
                    {t(`notice.kinds.${notice.kind}`)}
                  </span>
                </p>
              </div>

              <p className="text-sm font-semibold text-gray-900 mb-2">{notice.subject}</p>
              {/* The letter is plain text on purpose: the reference the investor retypes
                  must not be reflowed or hidden behind anything. */}
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-gray-800 bg-gray-50 border border-gray-200 rounded-xl p-4">
                {notice.body}
              </pre>

              {notice.qr_unavailable_reason && (
                <div className="mt-4">
                  <Notice tone="info" title={t('notice.noQr')}>
                    {notice.qr_unavailable_reason}
                  </Notice>
                </div>
              )}
              {!notice.sending_is_configured && (
                <div className="mt-4">
                  <Notice tone="warn" title={t('notice.sendingNotSetUp')}>
                    {t('notice.sendingNotSetUpHint')}
                  </Notice>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex justify-end gap-2 px-5 py-3.5 border-t border-gray-100 bg-gray-50">
          <Button variant="secondary" onClick={onClose}>
            {t('common.close')}
          </Button>
          <Button
            onClick={send}
            disabled={
              !notice || sending || !notice.sending_is_configured || !notice.to
            }
            leftIcon={<Send size={15} />}
          >
            {sending ? t('notice.sending') : t('notice.send')}
          </Button>
        </div>
      </div>
    </div>
  )
}

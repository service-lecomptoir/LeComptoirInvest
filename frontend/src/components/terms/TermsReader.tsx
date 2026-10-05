import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileText, X } from 'lucide-react'
import { errorMessage } from '@/api/client'
import type { TermsText } from '@/api/terms'
import { Loading, Notice } from '@/components/common/Primitives'
import { Button } from '@/components/ui'
import { numericDay } from '@/lib/format'

/** The layout of a text Alice serves as HTML: headings, paragraphs, lists, warning box, tables. */
const TERMS_LAYOUT = [
  '[&_h2]:mt-1 [&_h2]:mb-3 [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-brand-navy',
  '[&_h3]:mt-5 [&_h3]:mb-2 [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-brand-navy',
  '[&_h4]:mt-4 [&_h4]:mb-1 [&_h4]:font-semibold',
  '[&_p]:my-2 [&_strong]:font-semibold [&_strong]:text-gray-900',
  '[&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-5 [&_li]:my-1',
  '[&_blockquote]:my-3 [&_blockquote]:rounded-lg [&_blockquote]:border-l-4 [&_blockquote]:border-amber-400',
  '[&_blockquote]:bg-amber-50 [&_blockquote]:px-3 [&_blockquote]:py-1 [&_blockquote]:text-amber-900',
  '[&_hr]:my-4 [&_hr]:border-gray-200',
  '[&_table]:my-3 [&_table]:w-full [&_table]:text-xs [&_th]:border [&_th]:border-gray-200 [&_th]:bg-gray-50',
  '[&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_td]:border [&_td]:border-gray-200 [&_td]:px-2 [&_td]:py-1',
].join(' ')

/**
 * The body of a text: its version and date, what changed, the fall-back notice, the text.
 *
 * ⚠️ ALICE LAYS THE TEXT OUT ONCE FOR EVERY PRODUCT (`body_html`): she builds that HTML
 * from the ESCAPED Markdown source and emits only layout tags (h2-h4, p, strong, em, lists,
 * blockquote, hr, tables), so nothing in it can run. While she does not serve it yet, the
 * Markdown `body` (the binding text) is shown as written (`whitespace-pre-wrap`).
 */
export function TermsBody({ text, scroll = true }: { text: TermsText; scroll?: boolean }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">
        {t('terms.versionInForce', { version: text.version, date: numericDay(text.effective_from) })}
      </p>
      {text.fell_back && (
        <Notice tone="info" title={t('terms.fellBackTitle')}>
          {t('terms.fellBack')}
        </Notice>
      )}
      {text.summary_of_changes && (
        <div className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
          <p className="text-xs font-semibold text-gray-700">{t('terms.summary')}</p>
          <p className="mt-1 text-sm text-gray-700 whitespace-pre-wrap">{text.summary_of_changes}</p>
        </div>
      )}
      <div
        className={`break-words text-sm leading-relaxed text-gray-800 ${
          text.body_html ? TERMS_LAYOUT : 'whitespace-pre-wrap'
        } ${scroll ? 'max-h-[50vh] overflow-y-auto rounded-xl border border-gray-200 p-4' : ''}`}
        {...(text.body_html
          ? { dangerouslySetInnerHTML: { __html: text.body_html } }
          : { children: text.body })}
      />
    </div>
  )
}

/**
 * Reading a text without leaving the screen that asks for it.
 *
 * The house modal: it does NOT close on a click beside it (a stray tap would throw the
 * reading away), only on the cross, « Fermer » or Escape. Given the text already loaded
 * (the sign-up holds it), or a way to load it (an acceptance from the history).
 */
export function TermsReader({
  text: given,
  load,
  onClose,
}: {
  text?: TermsText
  load?: () => Promise<TermsText>
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [text, setText] = useState<TermsText | null>(given ?? null)
  const [refused, setRefused] = useState<string | null>(null)
  // ⚠️ READ ONCE, ON OPENING: a caller passing an arrow function would otherwise fetch the
  // text again on every render.
  const loadOnce = useRef(load)

  useEffect(() => {
    const run = loadOnce.current
    if (given || !run) return
    run()
      .then(setText)
      .catch((error) => setRefused(errorMessage(error)))
  }, [given])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-[80] grid place-items-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="terms-reader-title"
    >
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-xl overflow-hidden flex flex-col max-h-[90vh]">
        <div className="flex items-center justify-between gap-3 px-5 py-3.5 border-b border-gray-100">
          <div className="flex items-center gap-2 min-w-0">
            <FileText size={16} className="shrink-0 text-brand-navy" />
            <h2 id="terms-reader-title" className="text-[15px] font-semibold text-gray-900 truncate">
              {text?.title ?? t('terms.reading')}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('common.close')}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
          >
            <X size={16} />
          </button>
        </div>
        <div className="px-5 py-4 overflow-y-auto">
          {refused ? (
            <Notice tone="warn" title={t('terms.textUnavailable')}>
              {refused}
            </Notice>
          ) : text ? (
            <TermsBody text={text} scroll={false} />
          ) : (
            <Loading label={t('common.loading')} />
          )}
        </div>
        <div className="flex justify-end px-5 py-3 border-t border-gray-200 bg-gray-50">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.close')}
          </Button>
        </div>
      </div>
    </div>
  )
}

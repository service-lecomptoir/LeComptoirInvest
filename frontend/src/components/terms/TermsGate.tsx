import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { errorMessage } from '@/api/client'
import {
  termsApi, type TermsDocumentStatus, type TermsKind, type TermsStatus, type TermsText,
} from '@/api/terms'
import { pendingDocument } from '@/lib/terms'
import { LogoMark } from '@/components/common/Logo'
import { Loading, Notice } from '@/components/common/Primitives'
import { Button, Spinner } from '@/components/ui'
import { useAuthStore } from '@/store/authStore'
import { TermsBody } from './TermsReader'

/**
 * The full-page question, and nothing else of the application.
 *
 * Presentational: the text, the busy flag and the refusal are given. « J'accepte » sends
 * the version SHOWN; « Se déconnecter » is the product's own sign-out.
 */
export function TermsGateScreen({
  kind,
  document,
  text,
  refusal,
  busy,
  onAccept,
  onSignOut,
}: {
  kind: TermsKind
  document: TermsDocumentStatus
  text: TermsText | null
  refusal: string | null
  busy: boolean
  onAccept: () => void
  onSignOut: () => void
}) {
  const { t } = useTranslation()
  const changed = Boolean(document.accepted_version)
  return (
    <div className="min-h-screen bg-gray-50 px-4 py-8 sm:py-12">
      <div className="mx-auto w-full max-w-2xl">
        <div className="mb-6 flex items-center gap-2 text-brand-navy">
          <LogoMark size={26} className="shrink-0 text-brand-teal" />
          <span className="text-[15px] font-semibold">{t('brand.full')}</span>
        </div>
        <div className="rounded-2xl border border-gray-200 bg-white shadow-sm">
          <div className="px-5 pt-6 pb-4 sm:px-8">
            <h1 className="text-xl font-semibold text-gray-900">
              {changed ? t('terms.gate.titleChanged') : t('terms.gate.titleFirst')}
            </h1>
            <p className="mt-2 text-sm text-gray-600">
              {changed
                ? t(`terms.gate.subtitleChanged.${kind}`, { version: document.accepted_version })
                : t(`terms.gate.subtitleFirst.${kind}`)}
            </p>
            <p className="mt-4 text-sm font-semibold text-gray-900">{t(`terms.names.${kind}`)}</p>
          </div>
          <div className="px-5 pb-5 sm:px-8 space-y-4">
            {refusal && (
              <Notice tone="bad" title={t('terms.gate.refused')}>
                {refusal}
              </Notice>
            )}
            {text ? <TermsBody text={text} /> : <Loading label={t('common.loading')} />}
          </div>
          <div className="flex flex-col-reverse gap-2 border-t border-gray-200 bg-gray-50 px-5 py-4 sm:flex-row sm:justify-end sm:px-8 rounded-b-2xl">
            <Button type="button" variant="secondary" onClick={onSignOut}>
              {t('terms.gate.signOut')}
            </Button>
            <Button type="button" onClick={onAccept} disabled={!text} isLoading={busy}>
              {t('terms.gate.accept')}
            </Button>
          </div>
        </div>
        <p className="mt-3 text-xs text-gray-500">{t('terms.gate.help')}</p>
      </div>
    </div>
  )
}

/**
 * The door of the signed-in application: a version owed is accepted before anything else.
 *
 * 🔴 FAIL OPEN, ON PURPOSE. A console that does not answer (`unavailable`), a text that
 * cannot be read: the application opens, and the question comes back at the next sign-in.
 * An outage of the console must never lock a fund out of its own register.
 *
 * ⚠️ WHILE THE STATUS LOADS, THE PRODUCT'S OWN LOADING SCREEN, never the application then a
 * flash of the gate: a page shown and withdrawn reads like a fault.
 */
export function TermsGate({ children }: { children: ReactNode }) {
  const { i18n } = useTranslation()
  const navigate = useNavigate()
  const email = useAuthStore((state) => state.email)
  const logout = useAuthStore((state) => state.logout)
  const language = i18n.resolvedLanguage || i18n.language || 'fr'
  const [status, setStatus] = useState<TermsStatus | null | 'loading'>('loading')
  const [text, setText] = useState<TermsText | null>(null)
  const [textFailed, setTextFailed] = useState(false)
  const [refusal, setRefusal] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [textRead, setTextRead] = useState(0)

  const readStatus = useCallback(
    () =>
      termsApi
        .status()
        .then(({ data }) => setStatus(data))
        // Not even an answer from this server: nothing is known, nothing is asked.
        .catch(() => setStatus(null)),
    [],
  )

  // Once per signed-in account.
  useEffect(() => {
    setStatus('loading')
    void readStatus()
  }, [email, readStatus])

  const owed = status === 'loading' ? null : pendingDocument(status)
  const kind = owed?.kind
  const version = owed?.document.version
  const product = owed?.document.product
  const audience = owed?.document.audience

  useEffect(() => {
    if (!kind || !version) return
    let live = true
    setText(null)
    setTextFailed(false)
    termsApi
      .text({ kind, version, product, audience, language })
      .then(({ data }) => live && setText(data))
      .catch(() => live && setTextFailed(true))
    return () => {
      live = false
    }
  }, [kind, version, product, audience, language, textRead])

  if (status === 'loading') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-50 text-brand-navy">
        <Spinner size={24} />
      </div>
    )
  }
  // Nothing owed, the console silent, or a text it cannot serve: the application.
  if (!owed || textFailed) return <>{children}</>

  const accept = async () => {
    if (!text) return
    setBusy(true)
    setRefusal(null)
    try {
      await termsApi.accept({ kind: owed.kind, version: text.version, language })
      await readStatus()
    } catch (error: any) {
      setRefusal(errorMessage(error))
      // A 409: the version changed while the page was open. What is owed now is read
      // again, and its text with it.
      if (error?.response?.status === 409) {
        await readStatus()
        setTextRead((n) => n + 1)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <TermsGateScreen
      kind={owed.kind}
      document={owed.document}
      text={text}
      refusal={refusal}
      busy={busy}
      onAccept={accept}
      onSignOut={() => {
        logout()
        navigate('/login')
      }}
    />
  )
}

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileCheck2 } from 'lucide-react'
import { termsApi, type TermsAcceptance, type TermsKind } from '@/api/terms'
import { Card, Loading, Notice } from '@/components/common/Primitives'
import { useContactEmail } from '@/lib/contact'
import { instant, numericDay } from '@/lib/format'
import { useTermsOverview, type TermsOverview } from '@/lib/terms'
import { TermsReader } from './TermsReader'

/**
 * One document, read-only: the version accepted, when (date AND time, in the reader's
 * clock), the text itself, and the newer version when one is owed.
 *
 * 🔴 THERE IS NO « WITHDRAW » BUTTON. Withdrawing one's agreement to the terms is closing
 * the account; the help says how, in this product's own words.
 *
 * ⚠️ THE ADDRESS TO WRITE TO IS ALICE'S (`contact`, from `useContactEmail`), never one
 * written here: the help names none while none is known.
 */
export function AcceptedTermsView({
  kind,
  overview,
  onRead,
  contact = '',
}: {
  kind: TermsKind
  overview: TermsOverview | null
  onRead: (entry: TermsAcceptance) => void
  contact?: string
}) {
  const { t } = useTranslation()
  const history = overview?.history
  const latest = history?.entries.find((entry) => entry.kind === kind) ?? null
  const now = overview?.status?.[kind] ?? null
  // 🔴 « NEWER » IS ALICE'S ANSWER, NEVER A STRING COMPARISON (the owner, 11 Oct 2026).
  // A different version is not a later one: an account that accepted 2026-10 ahead of
  // its date was told « une nouvelle version 2026-09 est en vigueur ». Alice orders the
  // versions by effective date (`up_to_date`), and `pending` is its verdict.
  const newer = latest && now?.pending && now.version ? now : null
  const subscriber = overview?.status?.subscriber ?? false

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-gray-900">{t(`terms.accepted.title.${kind}`)}</h2>
      <Card>
        <div className="px-4 py-3 space-y-3">
          {!overview ? (
            <Loading label={t('common.loading')} />
          ) : history?.unavailable ? (
            <Notice tone="warn" title={t('terms.accepted.unavailableTitle')}>
              {t('terms.accepted.unavailable')}
            </Notice>
          ) : latest ? (
            <>
              <div className="flex items-start gap-3">
                <FileCheck2 size={16} className="mt-0.5 shrink-0 text-gray-400" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-gray-500">{t('terms.accepted.version')}</p>
                  <p className="text-sm text-gray-900 break-words">
                    {latest.title ? `${latest.title}, ` : ''}
                    {t('terms.accepted.versionNamed', { version: latest.version })}
                  </p>
                  <p className="mt-0.5 text-xs text-gray-500">
                    {t('terms.accepted.on', { when: instant(latest.accepted_at) })}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => onRead(latest)}
                className="text-sm text-brand-navy underline hover:no-underline"
              >
                {t('terms.readThis')}
              </button>
              {newer && (
                <Notice tone="info" title={t('terms.accepted.newerTitle')}>
                  {t('terms.accepted.newer', {
                    version: newer.version,
                    date: numericDay(newer.effective_from),
                  })}
                </Notice>
              )}
            </>
          ) : (
            <p className="text-sm text-gray-700">{t(`terms.accepted.none.${kind}`)}</p>
          )}
        </div>
      </Card>
      <p className="mt-2 text-xs text-gray-500 leading-relaxed">
        {t(subscriber ? 'terms.accepted.helpSubscriber' : 'terms.accepted.helpOther')}
        {contact &&
          ` ${t(subscriber ? 'terms.accepted.writeToSubscriber' : 'terms.accepted.writeToOther', { email: contact })}`}
      </p>
    </section>
  )
}

/** The section with its reader: the exact version accepted, in its own scope. */
export function AcceptedTerms({ kind, overview }: { kind: TermsKind; overview: TermsOverview | null }) {
  const { i18n } = useTranslation()
  const [reading, setReading] = useState<TermsAcceptance | null>(null)
  const contact = useContactEmail()
  const language = i18n.resolvedLanguage || i18n.language || 'fr'
  return (
    <>
      <AcceptedTermsView kind={kind} overview={overview} onRead={setReading} contact={contact} />
      {reading && (
        <TermsReader
          load={() =>
            termsApi
              .text({
                kind: reading.kind,
                version: reading.version,
                product: reading.product,
                audience: reading.audience,
                language,
              })
              .then(({ data }) => data)
          }
          onClose={() => setReading(null)}
        />
      )}
    </>
  )
}

/** « Conditions d'utilisation » in the profile of every account that signs in. */
export function TermsOfUseSection() {
  const overview = useTermsOverview()
  return <AcceptedTerms kind="cgu" overview={overview} />
}

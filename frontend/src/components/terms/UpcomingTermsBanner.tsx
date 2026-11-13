import { useContext, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileClock, X } from 'lucide-react'
import { termsApi, type TermsKind, type TermsUpcoming } from '@/api/terms'
import { numericDay } from '@/lib/format'
import { seenKeyOf, upcomingTerms } from '@/lib/terms'
import { TermsReader } from './TermsReader'
import { TermsStatusContext } from './termsStatusContext'

function wasSeen(key: string): boolean {
  try {
    return localStorage.getItem(key) === '1'
  } catch {
    return false
  }
}

/**
 * « Nouvelles conditions au JJ/MM/AAAA » on every page, during the notice of a new version
 * (terms of use, article 10.1: published and announced at least thirty days before it
 * takes effect, with a summary of what changes; the owner, 12 Nov 2026). « Lire » opens
 * the text announced with what changes; nothing is asked now: the version is asked at the
 * first sign-in from its date, by the gate. Set aside once read or hidden, per version.
 * Nothing while Alice is unreachable.
 */
export function UpcomingTermsBanner() {
  const { t, i18n } = useTranslation()
  const status = useContext(TermsStatusContext)
  const [, setTick] = useState(0)
  const [open, setOpen] = useState<{ kind: TermsKind; upcoming: TermsUpcoming } | null>(null)
  const items = upcomingTerms(status, wasSeen)
  if (items.length === 0 && !open) return null

  const setAside = (kind: TermsKind, version: string) => {
    try {
      localStorage.setItem(seenKeyOf(kind, version), '1')
    } catch {
      // A browser that refuses the storage shows the line again next time: harmless.
    }
    setTick((n) => n + 1)
  }
  // The reader's language, as the gate asks it: Alice serves French when she has none.
  const language = i18n.resolvedLanguage || i18n.language || 'fr'

  return (
    <>
      {items.map(({ kind, upcoming }) => (
        <div
          key={`${kind}-${upcoming.version}`}
          role="status"
          className="mx-4 mt-3 flex items-center gap-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900 sm:mx-6 lg:mx-8"
        >
          <FileClock size={16} className="shrink-0" />
          <span className="min-w-0 flex-1">
            {t('terms.upcoming.banner', { title: t(`terms.names.${kind}`), date: numericDay(upcoming.effective_from) })}
          </span>
          <button
            type="button"
            onClick={() => setOpen({ kind, upcoming })}
            className="shrink-0 rounded-lg border border-sky-300 bg-white px-3 py-1.5 font-medium hover:bg-sky-100"
          >
            {t('terms.upcoming.read')}
          </button>
          <button
            type="button"
            onClick={() => setAside(kind, upcoming.version)}
            aria-label={t('terms.upcoming.dismiss')}
            title={t('terms.upcoming.dismiss')}
            className="shrink-0 rounded p-1 hover:bg-sky-100"
          >
            <X size={14} />
          </button>
        </div>
      ))}
      {open && (
        <TermsReader
          ahead
          load={() =>
            termsApi
              .text({
                kind: open.kind,
                version: open.upcoming.version,
                product: open.upcoming.product,
                audience: open.upcoming.audience,
                language,
              })
              .then(({ data }) => data)
          }
          onClose={() => {
            setAside(open.kind, open.upcoming.version)
            setOpen(null)
          }}
        />
      )}
    </>
  )
}

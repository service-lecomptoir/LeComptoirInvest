import { useTranslation } from 'react-i18next'
import type { Subprocessor } from '@/api/terms'
import { InfoBubble } from '@/components/common/InfoBubble'
import { Loading, Notice } from '@/components/common/Primitives'
import { numericDay } from '@/lib/format'
import { useSubprocessors, type SubprocessorsState } from '@/lib/terms'

function Row({ row, from }: { row: Subprocessor; from?: string }) {
  const { t } = useTranslation()
  return (
    <li className="py-2">
      <p className="text-sm font-medium text-gray-900 break-words">{row.name}</p>
      <p className="text-xs text-gray-600 break-words">
        {t('terms.subprocessors.line', { service: row.service, location: row.location })}
      </p>
      {from && <p className="text-xs text-gray-500">{from}</p>}
    </li>
  )
}

/**
 * The sub-processors the data processing agreement authorises, under its text (the owner,
 * 13 Oct 2026): who, for what, where; then the additions announced, with their date.
 *
 * Presentational: the list is given. ⚠️ A list that cannot be read is said, never shown as
 * « no sub-processor ». The rows are Alice's own words (French), like the text.
 */
export function SubprocessorsView({ found }: { found: SubprocessorsState }) {
  const { t } = useTranslation()
  return (
    <section className="rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
      <div className="flex items-center gap-1.5">
        <h3 className="text-sm font-semibold text-gray-900">{t('terms.subprocessors.title')}</h3>
        <InfoBubble
          text={t('terms.subprocessors.info')}
          label={t('terms.subprocessors.infoLabel')}
          align="start"
        />
      </div>
      {found.state === 'loading' ? (
        <Loading label={t('common.loading')} />
      ) : found.state === 'unavailable' ? (
        <div className="mt-2">
          <Notice tone="warn" title={t('terms.subprocessors.unavailableTitle')}>
            {t('terms.subprocessors.unavailable')}
          </Notice>
        </div>
      ) : (
        <>
          {found.list.current.length ? (
            <ul className="mt-1 divide-y divide-gray-200">
              {found.list.current.map((row) => (
                <Row key={`${row.name}-${row.effective_from}`} row={row} />
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm text-gray-700">{t('terms.subprocessors.none')}</p>
          )}
          {found.list.announced.length > 0 && (
            <>
              <h4 className="mt-3 text-xs font-semibold text-gray-700">
                {t('terms.subprocessors.announcedTitle')}
              </h4>
              <ul className="divide-y divide-gray-200">
                {found.list.announced.map((row) => (
                  <Row
                    key={`${row.name}-${row.effective_from}`}
                    row={row}
                    from={t('terms.subprocessors.from', { date: numericDay(row.effective_from) })}
                  />
                ))}
              </ul>
            </>
          )}
          {found.list.contact_email && (
            <p className="mt-2 text-xs text-gray-500">
              {t('terms.subprocessors.objectTo', { email: found.list.contact_email })}
            </p>
          )}
        </>
      )}
    </section>
  )
}

/** The list, read from the console when it is shown. */
export function Subprocessors() {
  return <SubprocessorsView found={useSubprocessors()} />
}

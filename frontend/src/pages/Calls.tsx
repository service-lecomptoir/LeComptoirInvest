import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Wallet } from 'lucide-react'
import { treasuryApi } from '@/api'
import { Card, EmptyState, Loading, Notice, PageHeader } from '@/components/common/Primitives'
import { day, money } from '@/lib/format'
import type { CapitalCall } from '@/types'

/**
 * What the investor owes the fund, and — the point of the screen — the REFERENCE they have
 * to quote. A transfer arriving without it identifies the person but not the call, and the
 * fund is left choosing between four of their outstanding commitments.
 */
export default function Calls() {
  const { t } = useTranslation()
  const [calls, setCalls] = useState<CapitalCall[] | null>(null)

  useEffect(() => {
    treasuryApi.calls().then((r) => setCalls(r.data)).catch(() => setCalls([]))
  }, [])

  if (calls === null) return <Loading label={t('common.loading')} />

  return (
    <>
      <PageHeader title={t('calls.title')} subtitle={t('calls.subtitle')} />

      {calls.length === 0 ? (
        <Card>
          <EmptyState title={t('calls.none')} icon={<Wallet size={32} />}>
            {t('calls.noneBody')}
          </EmptyState>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {calls.map((c) => (
            <Card key={c.id} className="p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500">
                    {t('common.dueDate')}
                  </p>
                  <p className="mt-0.5 text-sm text-gray-900">{day(c.due_on)}</p>
                </div>
                <p className="text-xl font-semibold tabular-nums text-gray-900">
                  {money(c.amount, c.currency)}
                </p>
              </div>

              <div className="mt-4 rounded-lg bg-gray-50 border border-gray-200 px-3 py-2.5">
                <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500">
                  {t('common.reference')}
                </p>
                <p className="mt-0.5 font-mono text-base font-semibold tracking-wide text-brand-navy">
                  {c.reference}
                </p>
                <p className="mt-1.5 text-xs text-gray-500 leading-snug">{t('calls.referenceHelp')}</p>
              </div>

              {/* ⚠️ EPC069-12 IS EURO-ONLY. Drawing a code for an XOF call would encode an
                  amount the investor's bank reads as euros, so the fund shows the account
                  details instead and says why. */}
              {c.epc_qr ? (
                <div className="mt-4">
                  <p className="text-sm font-medium text-gray-900">{t('calls.qrTitle')}</p>
                  <p className="mt-0.5 text-xs text-gray-500 leading-snug">{t('calls.qrHelp')}</p>
                  <pre className="mt-2 overflow-x-auto rounded-lg bg-gray-900 text-gray-100 text-[11px] leading-relaxed p-3">
                    {c.epc_qr}
                  </pre>
                </div>
              ) : (
                <div className="mt-4">
                  <Notice tone="info" title={t('calls.qrTitle')}>{t('calls.qrEuroOnly')}</Notice>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </>
  )
}

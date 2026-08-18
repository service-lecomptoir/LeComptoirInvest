import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PieChart } from 'lucide-react'
import { subscriptionsApi } from '@/api'
import {
  Card, EmptyState, Kpi, KpiRow, Loading, PageHeader, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { money } from '@/lib/format'
import type { Portfolio as PortfolioData } from '@/types'

/**
 * The investor's home. Every figure here is RECOMPUTED from what happened — nothing is
 * stored — and the one they check first is the capital still at work: what they paid in,
 * less the capital already returned. If that number is wrong nothing else on the page
 * means anything.
 */
export default function Portfolio() {
  const { t } = useTranslation()
  const [data, setData] = useState<PortfolioData | null>(null)
  const [empty, setEmpty] = useState(false)

  useEffect(() => {
    subscriptionsApi
      .portfolio()
      .then((r) => setData(r.data))
      .catch(() => setEmpty(true))
  }, [])

  if (empty) {
    return (
      <>
        <PageHeader title={t('portfolio.title')} subtitle={t('portfolio.subtitle')} />
        <Card>
          <EmptyState title={t('portfolio.none')} icon={<PieChart size={32} />}>
            {t('portfolio.noneBody')}
          </EmptyState>
        </Card>
      </>
    )
  }
  if (!data) return <Loading label={t('common.loading')} />

  const currencies = Object.keys(data.totals_by_currency)

  return (
    <>
      <PageHeader title={t('portfolio.title')} subtitle={t('portfolio.subtitle')} />

      {currencies.length === 0 ? (
        <Card>
          <EmptyState title={t('portfolio.none')} icon={<PieChart size={32} />}>
            {t('portfolio.noneBody')}
          </EmptyState>
        </Card>
      ) : (
        currencies.map((currency) => {
          const block = data.totals_by_currency[currency]
          return (
            <div key={currency} className="mb-6">
              {/* One block per currency, never one figure: somebody holding euros and CFA
                  francs holds two portfolios, and adding them gives a number that is a
                  holding nowhere. It is also how their bank shows it. */}
              {currencies.length > 1 && (
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                  {t('dashboard.positionIn', { currency })}
                </p>
              )}
              <KpiRow>
                <Kpi
                  label={t('portfolio.atWork')}
                  value={money(block.capital_at_work, currency)}
                  hint={t('portfolio.atWorkHint')}
                />
                <Kpi
                  label={t('portfolio.received')}
                  value={money(block.income_received, currency)}
                  tone={Number(block.income_received) > 0 ? 'good' : 'neutral'}
                  hint={t('portfolio.receivedHint')}
                />
                <Kpi
                  label={t('portfolio.committed')}
                  value={money(block.committed, currency)}
                  hint={t('portfolio.committedHint')}
                />
                <Kpi
                  label={t('portfolio.remaining')}
                  value={money(block.outstanding_commitment, currency)}
                  tone={Number(block.outstanding_commitment) > 0 ? 'warn' : 'neutral'}
                  hint={t('portfolio.contributedHint')}
                />
              </KpiRow>
            </div>
          )
        })
      )}

      {data.positions.length > 0 && (
        <>
          <h2 className="text-sm font-semibold text-gray-900 mb-2">{t('portfolio.positions')}</h2>
          <TableWrap>
            <thead>
              <tr>
                <Th>{t('subscriptions.instrument')}</Th>
                <Th right>{t('portfolio.committed')}</Th>
                <Th right>{t('portfolio.called')}</Th>
                <Th right>{t('portfolio.contributed')}</Th>
                <Th right>{t('portfolio.atWork')}</Th>
                <Th right>{t('portfolio.received')}</Th>
                <Th right>{t('portfolio.netReceived')}</Th>
              </tr>
            </thead>
            <tbody>
              {data.positions.map((p) => (
                <tr key={p.subscription_id}>
                  <Td>{t(`subscriptions.instruments.${p.instrument}`, { defaultValue: p.instrument })}</Td>
                  <Td right>{money(p.committed, p.currency)}</Td>
                  <Td right>{money(p.called, p.currency)}</Td>
                  <Td right>{money(p.contributed, p.currency)}</Td>
                  <Td right className="font-medium">{money(p.capital_at_work, p.currency)}</Td>
                  <Td right className={Number(p.income_received) > 0 ? 'text-emerald-700' : ''}>
                    {money(p.income_received, p.currency)}
                  </Td>
                  <Td right>{money(p.net_received, p.currency)}</Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </>
      )}
    </>
  )
}

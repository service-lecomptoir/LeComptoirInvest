import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { FileText } from 'lucide-react'
import { statementsApi } from '@/api'
import { Select } from '@/components/ui'
import {
  Card, EmptyState, Loading, Notice, PageHeader, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { money } from '@/lib/format'
import type { Statement } from '@/types'

/**
 * The document an investor takes to their tax return.
 *
 * 🔴 THE YEAR IS THE YEAR OF PAYMENT, NEVER OF DECISION, and the screen says so out loud.
 * A distribution decided on 28 December and paid on 4 January belongs to the second year,
 * because that is when the investor had the money. What was decided and not paid is shown
 * SEPARATELY and added to nothing.
 */
export default function StatementPage() {
  const { t } = useTranslation()
  const thisYear = new Date().getFullYear()
  const [year, setYear] = useState(String(thisYear))
  const [data, setData] = useState<Statement | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    statementsApi
      .get(Number(year))
      .then((r) => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [year])

  const years = Array.from({ length: 6 }, (_, i) => String(thisYear - i))
  const currencies = data ? Object.keys(data.totals_by_currency) : []
  const pending = data ? Object.entries(data.decided_not_paid) : []

  return (
    <>
      <PageHeader
        title={t('statement.title')}
        subtitle={t('statement.subtitle')}
        actions={
          <div className="min-w-[8rem]">
            <Select
              value={year}
              onChange={setYear}
              options={years.map((y) => ({ value: y, label: y }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
              aria-label={t('common.year')}
            />
          </div>
        }
      />

      <p className="-mt-3 mb-5 text-xs text-gray-500">{t('statement.yearHint')}</p>

      {loading ? (
        <Loading label={t('common.loading')} />
      ) : !data || data.lines.length === 0 ? (
        <Card>
          <EmptyState title={t('statement.none', { year })} icon={<FileText size={32} />}>
            {t('statement.noneBody')}
          </EmptyState>
        </Card>
      ) : (
        <>
          <TableWrap>
            <thead>
              <tr>
                <Th>{t('subscriptions.instrument')}</Th>
                <Th>{t('common.currency')}</Th>
                <Th right>{t('statement.grossIncome')}</Th>
                <Th right>{t('statement.withholding')}</Th>
                <Th right>{t('statement.netIncome')}</Th>
                <Th right>{t('statement.capitalRepaid')}</Th>
                <Th right>{t('statement.receivedTotal')}</Th>
              </tr>
            </thead>
            <tbody>
              {data.lines.map((line, i) => (
                <tr key={i}>
                  <Td>
                    {t(`subscriptions.instruments.${line.instrument}`, { defaultValue: line.instrument })}
                  </Td>
                  <Td className="text-gray-500">{line.currency}</Td>
                  <Td right className="font-medium">{money(line.income_gross, line.currency)}</Td>
                  <Td right className="text-gray-500">{money(line.withholding, line.currency)}</Td>
                  <Td right>{money(line.income_net, line.currency)}</Td>
                  <Td right className="text-gray-500">{money(line.capital_repaid, line.currency)}</Td>
                  <Td right>{money(line.received, line.currency)}</Td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              {currencies.map((currency) => {
                const block = data.totals_by_currency[currency]
                return (
                  <tr key={currency} className="bg-gray-50 font-semibold">
                    <Td className="text-gray-900">{t('common.total')}</Td>
                    <Td className="text-gray-500">{currency}</Td>
                    <Td right>{money(block.income_gross, currency)}</Td>
                    <Td right>{money(block.withholding, currency)}</Td>
                    <Td right>
                      {money(Number(block.income_gross) - Number(block.withholding), currency)}
                    </Td>
                    <Td right>{money(block.capital_repaid, currency)}</Td>
                    <Td right>{money(block.received, currency)}</Td>
                  </tr>
                )
              })}
            </tfoot>
          </TableWrap>

          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            <Notice tone="info" title={t('statement.capitalRepaid')}>
              {t('statement.capitalIsNotIncome')}
            </Notice>
            {Object.keys(data.capital_at_work).length > 0 && (
              <Card className="px-4 py-3">
                <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500">
                  {t('statement.atWorkAtYearEnd')}
                </p>
                <div className="mt-1.5 space-y-0.5">
                  {Object.entries(data.capital_at_work).map(([currency, value]) => (
                    <p key={currency} className="text-base font-semibold tabular-nums text-gray-900">
                      {money(value, currency)}
                    </p>
                  ))}
                </div>
              </Card>
            )}
          </div>

          {pending.length > 0 && (
            <div className="mt-4">
              <Notice tone="warn" title={t('statement.decidedNotPaidTitle')}>
                <p>{t('statement.decidedNotPaidBody')}</p>
                <ul className="mt-2 space-y-0.5">
                  {pending.map(([currency, value]) => (
                    <li key={currency} className="font-semibold tabular-nums">
                      {money(value, currency)}
                    </li>
                  ))}
                </ul>
              </Notice>
            </div>
          )}
        </>
      )}
    </>
  )
}

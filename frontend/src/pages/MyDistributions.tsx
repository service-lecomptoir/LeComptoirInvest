import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Banknote } from 'lucide-react'
import { distributionsApi } from '@/api'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { day, money } from '@/lib/format'
import type { Distribution } from '@/types'

/**
 * What the fund paid this investor, with capital and income kept apart on screen exactly
 * as they are kept apart in the database. Getting your own money back is not a gain, and a
 * single « received » column is how an investor comes to believe it was one.
 */
export default function MyDistributions() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<Distribution[] | null>(null)

  useEffect(() => {
    distributionsApi.list().then((r) => setRows(r.data)).catch(() => setRows([]))
  }, [])

  if (rows === null) return <Loading label={t('common.loading')} />

  return (
    <>
      <PageHeader title={t('myDistributions.title')} subtitle={t('myDistributions.subtitle')} />

      {rows.length === 0 ? (
        <Card>
          <EmptyState title={t('myDistributions.none')} icon={<Banknote size={32} />}>
            {t('myDistributions.noneBody')}
          </EmptyState>
        </Card>
      ) : (
        <>
          <TableWrap>
            <thead>
              <tr>
                <Th>{t('distributions.decidedOn')}</Th>
                <Th right>{t('common.capital')}</Th>
                <Th right>{t('common.income')}</Th>
                <Th right>{t('distributions.withholding')}</Th>
                <Th>{t('common.status')}</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((d) => (
                <tr key={d.id}>
                  <Td className="text-gray-500 whitespace-nowrap">{day(d.decided_on)}</Td>
                  <Td right>{money(d.capital_amount, d.currency)}</Td>
                  <Td right className={Number(d.income_amount) > 0 ? 'text-emerald-700 font-medium' : ''}>
                    {money(d.income_amount, d.currency)}
                  </Td>
                  <Td right className="text-gray-500">{money(d.withholding_amount, d.currency)}</Td>
                  <Td>
                    {/* A distribution decided and not yet sent is a real state, and it must
                        not look like a payment: the money is still in the fund's account. */}
                    {d.paid_on ? (
                      <Pill tone="good">{t('distributions.paidOn', { date: day(d.paid_on) })}</Pill>
                    ) : (
                      <Pill tone="warn">{t('distributions.notPaid')}</Pill>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>

          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <Notice tone="info" title={t('common.capital')}>{t('myDistributions.capitalHint')}</Notice>
            <Notice tone="info" title={t('common.income')}>{t('myDistributions.incomeHint')}</Notice>
          </div>
        </>
      )}
    </>
  )
}

import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ArrowDown, Ban, Check, Landmark, Users } from 'lucide-react'
import clsx from 'clsx'
import { distributionsApi } from '@/api'
import { errorMessage } from '@/api/client'
import { Button, Input, Select } from '@/components/ui'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { day, money } from '@/lib/format'
import { toast } from '@/store/toast'
import type { Distribution, Waterfall, WaterfallShare } from '@/types'

const CURRENCIES = ['EUR', 'XOF', 'USD', 'GBP', 'MAD', 'XAF']
const FIELD = 'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white'

/**
 * THE SCREEN THAT SHOWS THE RULE.
 *
 * Everything else in this product records facts. This one applies the only rule the fund
 * cannot get wrong, and the design follows from that: the two tiers are drawn as tiers,
 * the debt is shown even when it is covered, and a refusal takes the whole width instead
 * of being a red line under a field.
 *
 * ⚠️ WHAT IS SHOWN IS A PROPOSAL. The server runs the waterfall again when the fund
 * decides, and writes what IT computes — never the shares this page is holding. A screen
 * that posted its own numbers would let the one rule this product exists to enforce be
 * edited in a developer console.
 */
export default function Distributions() {
  const { t } = useTranslation()
  const today = new Date().toISOString().slice(0, 10)
  const [currency, setCurrency] = useState('EUR')
  const [amount, setAmount] = useState('')
  const [asOf, setAsOf] = useState(today)
  const [repayCapital, setRepayCapital] = useState(false)

  const [waterfall, setWaterfall] = useState<Waterfall | null>(null)
  const [refusal, setRefusal] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [history, setHistory] = useState<Distribution[] | null>(null)

  const loadHistory = () => {
    distributionsApi.list().then((r) => setHistory(r.data)).catch(() => setHistory([]))
  }
  useEffect(loadHistory, [])

  const propose = async () => {
    setBusy(true)
    setRefusal(null)
    try {
      const { data } = await distributionsApi.propose({
        currency, amount, as_of: asOf, repay_capital: repayCapital,
      })
      setWaterfall(data)
    } catch (err) {
      setWaterfall(null)
      setRefusal(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const decide = async () => {
    if (!waterfall) return
    setBusy(true)
    try {
      await distributionsApi.decide({
        currency, amount, as_of: asOf, repay_capital: repayCapital, decided_on: today,
      })
      toast.success(t('distributions.decided'))
      setWaterfall(null)
      setAmount('')
      loadHistory()
    } catch {
      // The interceptor already showed the server's sentence.
    } finally {
      setBusy(false)
    }
  }

  const lenders = waterfall?.shares.filter((s) => s.instrument === 'loan') ?? []
  const members = waterfall?.shares.filter((s) => s.instrument === 'equity') ?? []

  return (
    <>
      <PageHeader title={t('distributions.title')} subtitle={t('distributions.subtitle')} />

      <Card className="p-4 mb-6">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('common.currency')}</label>
            <Select
              value={currency}
              onChange={setCurrency}
              options={CURRENCIES.map((c) => ({ value: c, label: c }))}
              className={FIELD}
            />
          </div>
          <Input
            label={t('distributions.amountToDistribute')}
            type="number"
            min="0"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <Input
            label={t('distributions.asOf')}
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
            hint={t('distributions.asOfHint')}
          />
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{t('distributions.nature')}</label>
            <Select
              value={repayCapital ? 'capital' : 'income'}
              onChange={(v) => setRepayCapital(v === 'capital')}
              options={[
                { value: 'income', label: t('distributions.natureIncome') },
                { value: 'capital', label: t('distributions.natureCapital') },
              ]}
              className={FIELD}
            />
          </div>
          <Button onClick={propose} isLoading={busy} disabled={!amount}>
            {t('distributions.compute')}
          </Button>
        </div>
        {/* The tool does not infer this: paying out a year's profits and winding a project
            down look identical from the amount alone, and guessing would mislabel capital
            as income on somebody's tax statement. */}
        <p className="mt-3 text-xs text-gray-500">
          {repayCapital ? t('distributions.natureCapitalHelp') : t('distributions.natureIncomeHelp')}
        </p>
      </Card>

      {refusal && (
        <div className="mb-6">
          <Notice tone="bad" title={t('distributions.impossible')}>{refusal}</Notice>
        </div>
      )}

      {busy && !waterfall && <Loading label={t('distributions.computing')} />}

      {waterfall && (
        <div className="mb-8">
          {waterfall.unknown.length > 0 && (
            <div className="mb-4">
              <Notice tone="bad" title={t('distributions.unmeasurableTitle')}>
                <ul className="list-disc pl-5 space-y-0.5">
                  {waterfall.unknown.map((u, i) => <li key={i}>{u}</li>)}
                </ul>
              </Notice>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-3 mb-4">
            {[
              [t('distributions.available'), waterfall.available],
              [t('distributions.allocated'), waterfall.distributed],
              [t('distributions.keptByFund'), waterfall.undistributed],
            ].map(([label, value]) => (
              <Card key={label as string} className="px-4 py-3">
                <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500">{label}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {money(value as string, waterfall.currency)}
                </p>
              </Card>
            ))}
          </div>

          <Tier
            rank={1}
            icon={<Landmark size={15} />}
            title={t('distributions.lenders')}
            caption={t('distributions.lendersCaption')}
            shares={lenders}
            currency={waterfall.currency}
            state={Number(waterfall.debt_remaining) > 0 ? 'short' : 'served'}
            footnote={
              Number(waterfall.debt_remaining) > 0
                ? t('distributions.stillOwed', {
                    amount: money(waterfall.debt_remaining, waterfall.currency),
                  })
                : t('distributions.debtCovered')
            }
          />

          <div className="flex justify-center py-2">
            <ArrowDown size={18} className={clsx(waterfall.blocked_reason ? 'text-red-400' : 'text-gray-300')} />
          </div>

          {waterfall.blocked_reason && members.length === 0 ? (
            <div className="border-2 border-dashed border-red-200 bg-red-50/50 rounded-xl px-4 py-5">
              <div className="flex items-start gap-3">
                <Ban size={18} className="mt-0.5 shrink-0 text-red-600" />
                <div>
                  <p className="text-sm font-semibold text-red-900">{t('distributions.blockedTitle')}</p>
                  <p className="mt-1 text-sm text-red-800 leading-relaxed">{waterfall.blocked_reason}</p>
                  <p className="mt-2 text-xs text-red-700/80 leading-relaxed">{t('distributions.blockedWhy')}</p>
                </div>
              </div>
            </div>
          ) : (
            <Tier
              rank={2}
              icon={<Users size={15} />}
              title={t('distributions.members')}
              caption={t('distributions.membersCaption')}
              shares={members}
              currency={waterfall.currency}
              state={members.length ? 'served' : 'empty'}
              footnote={waterfall.blocked_reason ?? undefined}
            />
          )}

          {waterfall.shares.length > 0 && (
            <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-gray-500 max-w-xl">{t('distributions.decideHelp')}</p>
              <Button onClick={decide} isLoading={busy}>
                <Check size={15} /> {t('distributions.decide')}
              </Button>
            </div>
          )}
        </div>
      )}

      <h2 className="text-sm font-semibold text-gray-900 mb-2">{t('distributions.history')}</h2>
      {history === null ? (
        <Loading label={t('common.loading')} />
      ) : history.length === 0 ? (
        <Card>
          <EmptyState title={t('distributions.none')}>{t('distributions.noneBody')}</EmptyState>
        </Card>
      ) : (
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
            {history.map((d) => (
              <tr key={d.id}>
                <Td className="text-gray-500 whitespace-nowrap">{day(d.decided_on)}</Td>
                <Td right>{money(d.capital_amount, d.currency)}</Td>
                <Td right>{money(d.income_amount, d.currency)}</Td>
                <Td right className="text-gray-500">{money(d.withholding_amount, d.currency)}</Td>
                <Td>
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
      )}
    </>
  )
}

function Tier({
  rank, icon, title, caption, shares, currency, state, footnote,
}: {
  rank: number
  icon: React.ReactNode
  title: string
  caption: string
  shares: WaterfallShare[]
  currency: string
  state: 'served' | 'short' | 'empty'
  footnote?: string
}) {
  const { t } = useTranslation()
  const border = { served: 'border-emerald-200', short: 'border-amber-300', empty: 'border-gray-200' }[state]
  return (
    <Card className={clsx('overflow-hidden border-2', border)}>
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2.5">
          <span className="grid place-items-center w-6 h-6 rounded-full bg-brand-navy text-white text-[11px] font-semibold">
            {rank}
          </span>
          <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-gray-900">
            {icon} {title}
          </span>
        </div>
        <p className="text-xs text-gray-500">{caption}</p>
      </div>
      {shares.length === 0 ? (
        <p className="px-4 py-4 text-sm text-gray-500">{t('distributions.nothingAtRank')}</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr>
              <Th>{t('common.investor')}</Th>
              <Th right>{t('common.capital')}</Th>
              <Th right>{t('common.income')}</Th>
              <Th right>{t('common.total')}</Th>
            </tr>
          </thead>
          <tbody>
            {shares.map((s) => (
              <tr key={s.subscription_id}>
                <Td>{s.investor_name}</Td>
                <Td right>{money(s.capital_amount, currency)}</Td>
                <Td right>{money(s.income_amount, currency)}</Td>
                <Td right className="font-medium">
                  {money(Number(s.capital_amount) + Number(s.income_amount), currency)}
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {footnote && (
        <p
          className={clsx(
            'px-4 py-2.5 text-xs border-t',
            state === 'short'
              ? 'bg-amber-50 text-amber-900 border-amber-200'
              : 'bg-gray-50 text-gray-600 border-gray-200',
          )}
        >
          {footnote}
        </p>
      )}
    </Card>
  )
}

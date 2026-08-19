import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Layers, Landmark } from 'lucide-react'
import { fundsApi } from '@/api'
import { Button, Input, Select } from '@/components/ui'
import {
  Card, EmptyState, Kpi, KpiRow, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { money, day } from '@/lib/format'
import { toast } from '@/store/toast'
import type { Fund, FundNetAssetValue, FundStatus } from '@/types'

const STATUSES: FundStatus[] = ['raising', 'investing', 'harvesting', 'closed']

/**
 * The vehicles: what groups projects and subscribers, and whose terms they share.
 *
 * 🔴 THE SCREEN EXISTS SO THE SCOPE CAN BE SEEN. The waterfall, the net asset value and the
 * performance are all computed PER VEHICLE on the server. Without a screen naming the
 * vehicles, that scope is a parameter nobody can set — and the product silently answers for
 * « the fund with no row », which is right today and wrong the day a second one opens.
 *
 * ⚠️ AND THE ACCOUNT IS SHOWN NEXT TO THE NAME, not buried in a form. Cash is the one thing
 * that cannot be split by a rule: a bank line says nothing about which vehicle the euro was
 * for. Two funds on one account therefore have NO computable net asset value, and this page
 * says so in the row rather than letting the figure page fail later.
 */
export default function Funds() {
  const { t } = useTranslation()
  const [funds, setFunds] = useState<Fund[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({
    name: '', currency: 'EUR', iban: '',
    preferred_return: '', carried_interest: '', management_fee: '', mandate: '',
  })

  const today = new Date().toISOString().slice(0, 10)
  const [asOf, setAsOf] = useState(today)
  const [selected, setSelected] = useState<string>('')
  const [value, setValue] = useState<FundNetAssetValue | null>(null)
  const [valuing, setValuing] = useState(false)

  const load = () => fundsApi.list().then((r) => setFunds(r.data)).catch(() => setFunds([]))
  useEffect(() => { void load() }, [])

  const chosen = (funds ?? []).find((f) => f.id === selected) ?? null
  const currency = chosen?.currency ?? 'EUR'

  useEffect(() => {
    if (!asOf) return
    setValuing(true)
    fundsApi
      .netAssetValue({ as_of: asOf, currency, fund_id: selected || undefined })
      .then((r) => setValue(r.data[0] ?? null))
      .catch(() => setValue(null))
      .finally(() => setValuing(false))
  }, [asOf, currency, selected])

  /** A percentage typed as « 8 » means eight per cent, and the API stores a rate. Converting
   *  here rather than asking the user to type 0.08 is the difference between a hurdle and a
   *  hundred-fold error that reads as a plausible number. */
  const rate = (typed: string) => (typed.trim() === '' ? 0 : Number(typed) / 100)

  const submit = async () => {
    if (!form.name.trim()) return
    const terms =
      form.preferred_return || form.carried_interest || form.management_fee
        ? {
            preferred_return: rate(form.preferred_return),
            carried_interest: rate(form.carried_interest),
            management_fee: rate(form.management_fee),
          }
        : null
    try {
      await fundsApi.create({
        name: form.name.trim(),
        currency: form.currency.toUpperCase(),
        iban: form.iban.trim() || null,
        terms,
        opened_on: today,
        mandate: form.mandate.trim() || null,
      })
      setCreating(false)
      setForm({
        name: '', currency: 'EUR', iban: '',
        preferred_return: '', carried_interest: '', management_fee: '', mandate: '',
      })
      await load()
    } catch {
      // The interceptor already showed the server's sentence, which says more than any
      // second message written here could.
    }
  }

  const setStatus = async (fund: Fund, status: FundStatus) => {
    try {
      await fundsApi.setStatus(fund.id, {
        status,
        closed_on: status === 'closed' ? today : null,
      })
      toast.success(t('funds.statusChanged', { name: fund.name }))
      await load()
    } catch {
      /* the server said why */
    }
  }

  const pct = (value: number | undefined) =>
    value == null ? '-' : `${(value * 100).toFixed(2)} %`

  return (
    <>
      <PageHeader
        title={t('funds.title')}
        subtitle={t('funds.subtitle')}
        actions={
          <Button onClick={() => setCreating((open) => !open)}>
            {creating ? t('common.cancel') : t('funds.open')}
          </Button>
        }
      />

      {creating && (
        <Card className="mb-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              label={t('funds.name')}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <Input
              label={t('funds.currency')}
              value={form.currency}
              maxLength={3}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
            />
            <div className="sm:col-span-2">
              <Input
                label={t('funds.iban')}
                hint={t('funds.ibanHint')}
                value={form.iban}
                onChange={(e) => setForm({ ...form, iban: e.target.value })}
              />
            </div>
            <Input
              label={t('funds.preferredReturn')}
              type="number"
              value={form.preferred_return}
              onChange={(e) => setForm({ ...form, preferred_return: e.target.value })}
            />
            <Input
              label={t('funds.carriedInterest')}
              type="number"
              value={form.carried_interest}
              onChange={(e) => setForm({ ...form, carried_interest: e.target.value })}
            />
            <Input
              label={t('funds.managementFee')}
              type="number"
              value={form.management_fee}
              onChange={(e) => setForm({ ...form, management_fee: e.target.value })}
            />
            <Input
              label={t('funds.mandate')}
              value={form.mandate}
              onChange={(e) => setForm({ ...form, mandate: e.target.value })}
            />
          </div>
          <div className="mt-4 flex justify-end">
            <Button onClick={submit} disabled={!form.name.trim()}>
              {t('funds.open')}
            </Button>
          </div>
        </Card>
      )}

      {funds === null ? (
        <Loading label={t('common.loading')} />
      ) : funds.length === 0 ? (
        <Card>
          <EmptyState title={t('funds.none')} icon={<Layers size={28} />}>
            {t('funds.noneHint')}
          </EmptyState>
        </Card>
      ) : (
        <>
          <Card className="mb-5">
            <TableWrap>
              <thead>
                <tr>
                  <Th>{t('funds.name')}</Th>
                  <Th>{t('funds.status')}</Th>
                  <Th>{t('funds.currency')}</Th>
                  <Th>{t('funds.iban')}</Th>
                  <Th>{t('funds.terms')}</Th>
                  <Th>{t('funds.opened')}</Th>
                  <Th> </Th>
                </tr>
              </thead>
              <tbody>
                {funds.map((fund) => (
                  <tr key={fund.id} className="border-t border-gray-100">
                    <Td>
                      <span className="font-medium text-gray-900">{fund.name}</span>
                      {!fund.cash_is_separable && (
                        <span className="block text-xs text-amber-700 mt-0.5">
                          {t('funds.cashNotSeparable')}
                        </span>
                      )}
                    </Td>
                    <Td>
                      <Pill tone={fund.status === 'closed' ? 'neutral' : 'good'}>
                        {t(`funds.statuses.${fund.status}`)}
                      </Pill>
                    </Td>
                    <Td>{fund.currency}</Td>
                    <Td>
                      {fund.iban ? (
                        <span className="font-mono text-xs">{fund.iban}</span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </Td>
                    <Td>
                      {fund.terms ? (
                        <span className="text-xs text-gray-600">
                          {t('funds.hurdle')} {pct(fund.terms.preferred_return)} ·{' '}
                          {t('funds.carry')} {pct(fund.terms.carried_interest)} ·{' '}
                          {t('funds.fee')} {pct(fund.terms.management_fee)}
                        </span>
                      ) : (
                        <span className="text-gray-400">{t('funds.noTerms')}</span>
                      )}
                    </Td>
                    <Td>{fund.opened_on ? day(fund.opened_on) : '-'}</Td>
                    <Td>
                      <div className="min-w-[9rem]">
                        <Select
                          value={fund.status}
                          onChange={(next) => void setStatus(fund, next as FundStatus)}
                          options={STATUSES.map((s) => ({
                            value: s,
                            label: t(`funds.statuses.${s}`),
                          }))}
                          className="w-full px-2 py-1.5 border border-gray-300 rounded-lg text-sm bg-white"
                          aria-label={t('funds.status')}
                        />
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Card>

          <Card>
            <div className="flex flex-wrap items-end gap-3 mb-4">
              <div className="min-w-[12rem]">
                <Select
                  value={selected}
                  onChange={setSelected}
                  options={[
                    { value: '', label: t('funds.unattached') },
                    ...funds.map((f) => ({ value: f.id, label: f.name })),
                  ]}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
                  aria-label={t('funds.whichVehicle')}
                />
              </div>
              <div className="min-w-[11rem]">
                <Input
                  label={t('funds.asOf')}
                  type="date"
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value)}
                />
              </div>
            </div>

            {valuing ? (
              <Loading label={t('common.loading')} />
            ) : !value ? (
              <EmptyState title={t('funds.noValue')} icon={<Landmark size={28} />}>
                {t('funds.noValueHint')}
              </EmptyState>
            ) : (
              <>
                <KpiRow>
                  <Kpi label={t('funds.projects')} value={money(value.projects, value.currency)} />
                  <Kpi label={t('funds.cash')} value={money(value.cash, value.currency)} />
                  <Kpi
                    label={t('funds.debt')}
                    value={money(value.debt_to_lenders, value.currency)}
                  />
                  <Kpi
                    label={t('funds.netAssetValue')}
                    value={value.total == null ? '-' : money(value.total, value.currency)}
                  />
                </KpiRow>
                {value.unavailable_reason && (
                  <div className="mt-4">
                    {/* 🔴 THE REASON IS THE ANSWER. A dash with no sentence sends the reader
                        looking for a bug; the sentence sends them to the project nobody
                        valued, which is the one thing that would produce the figure. */}
                    <Notice tone="warn" title={t('funds.cannotTotal')}>
                      {value.unavailable_reason}
                      {value.unvalued.length > 0 && (
                        <span className="block mt-1 font-medium">
                          {value.unvalued.join(', ')}
                        </span>
                      )}
                    </Notice>
                  </div>
                )}
              </>
            )}
          </Card>
        </>
      )}
    </>
  )
}

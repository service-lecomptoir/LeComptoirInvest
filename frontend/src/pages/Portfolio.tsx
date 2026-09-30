import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { PieChart, Plus, ShieldCheck, ShieldQuestion } from 'lucide-react'
import { investorsApi, subscriptionsApi } from '@/api'
import { Button, Input, Select } from '@/components/ui'
import {
  Card, EmptyState, Kpi, KpiRow, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { money } from '@/lib/format'
import { toast } from '@/store/toast'
import type { Investor, Portfolio as PortfolioData } from '@/types'

const CURRENCIES = ['EUR', 'XOF', 'USD', 'GBP', 'MAD', 'XAF']

/**
 * The space of the investor. Every figure is RECOMPUTED from what happened -- nothing is
 * stored -- and the one they look at first is the capital still at work: what they paid in,
 * less the capital already returned. If that number is wrong, nothing else on the page
 * means anything at all.
 */
export default function Portfolio() {
  const { t } = useTranslation()
  const [data, setData] = useState<PortfolioData | null>(null)
  const [me, setMe] = useState<Investor | null>(null)
  const [empty, setEmpty] = useState(false)
  const [asking, setAsking] = useState(false)

  const load = () => {
    subscriptionsApi
      .portfolio()
      .then((r) => setData(r.data))
      .catch(() => setEmpty(true))
    // Their own file: a blocked investor must know WHY they are, rather than running
    // into a refusal without an explanation at the moment of subscribing.
    investorsApi.me().then((r) => setMe(r.data)).catch(() => setMe(null))
  }
  useEffect(load, [])

  const accepted = me?.kyc_status === 'accepted'

  const header = (
    <PageHeader
      title={t('portfolio.title')}
      subtitle={t('portfolio.subtitle')}
      actions={
        !asking ? (
          <Button size="sm" onClick={() => setAsking(true)} disabled={!accepted}>
            <Plus size={15} /> {t('invest.action')}
          </Button>
        ) : undefined
      }
    />
  )

  const fileState = me && (
    <div className="mb-6">
      <Notice
        tone={accepted ? 'info' : 'warn'}
        title={t('invest.myFile')}
      >
        <span className="inline-flex items-center gap-2">
          <Pill tone={accepted ? 'good' : 'warn'}>
            {accepted ? <ShieldCheck size={11} /> : <ShieldQuestion size={11} />}{' '}
            {t(`investors.kyc.${me.kyc_status}`, { defaultValue: me.kyc_status })}
          </Pill>
          {accepted ? t('invest.fileAccepted') : t('invest.blocked')}
        </span>
      </Notice>
    </div>
  )

  const askForm = asking && (
    <div className="mb-6">
      <AskToSubscribe onCancel={() => setAsking(false)} onDone={() => { setAsking(false); load() }} />
    </div>
  )

  if (empty || (data && Object.keys(data.totals_by_currency).length === 0)) {
    return (
      <>
        {header}
        {fileState}
        {askForm}
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
      {header}
      {fileState}
      {askForm}

      {currencies.map((currency) => {
        const block = data.totals_by_currency[currency]
        return (
          <div key={currency} className="mb-6">
            {/* One block per currency, never a single figure: holding euros and CFA
                francs is holding two portfolios, and adding them up gives a number that is
                an asset nowhere. That is also how the bank presents it. */}
            {currencies.length > 1 && (
              <p className="mb-2 text-[11px] font-semibold text-gray-500">
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
      })}

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

/**
 * « Investir en ligne » -- the screen the product promised and did not have.
 *
 * 🔴 THIS FORM WRITES A REQUEST, NEVER A COMMITMENT. If it created a subscription, whoever
 * holds an id would create a binding commitment of the fund -- and an investor nobody has
 * checked would do so before anybody had looked at who they are. It is the fund that
 * accepts, and that acceptance alone is what binds.
 *
 * ⚠️ THE VERSION OF THE INFORMATION DOCUMENT IS RECORDED NOW, not found again later. The
 * document changes; « ce qu'on lui a montré » is answerable only if it was written down at
 * that moment.
 */
function AskToSubscribe({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [instrument, setInstrument] = useState('equity')
  const [amount, setAmount] = useState('')
  const [currency, setCurrency] = useState('EUR')
  const [documentVersion, setDocumentVersion] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await subscriptionsApi.request({
        instrument,
        amount,
        currency,
        information_document_version: documentVersion.trim() || undefined,
      })
      toast.success(t('invest.sent'))
      onDone()
    } catch {
      /* the message of the server is already shown by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-4 border-brand-navy/30">
      <p className="text-sm font-semibold text-gray-900">{t('invest.title')}</p>
      <p className="mt-0.5 mb-3 text-xs text-gray-500 max-w-2xl">{t('invest.explain')}</p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-5 items-end">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('invest.instrument')}
          </label>
          <Select
            value={instrument}
            onChange={setInstrument}
            options={[
              { value: 'equity', label: t('subscriptions.instruments.equity') },
              { value: 'loan', label: t('subscriptions.instruments.loan') },
            ]}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
          />
        </div>
        <Input
          label={t('invest.amount')}
          type="number"
          min="0"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          required
        />
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            {t('invest.currency')}
          </label>
          <Select
            value={currency}
            onChange={setCurrency}
            options={CURRENCIES.map((c) => ({ value: c, label: c }))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
          />
        </div>
        <Input
          label={t('invest.documentVersion')}
          value={documentVersion}
          onChange={(e) => setDocumentVersion(e.target.value)}
        />
        <div className="flex gap-2">
          <Button type="submit" isLoading={busy}>{t('common.confirm')}</Button>
          <Button type="button" variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button>
        </div>
      </form>
      <p className="mt-3 text-xs text-gray-500 max-w-3xl leading-relaxed">{t('invest.documentHint')}</p>
    </Card>
  )
}

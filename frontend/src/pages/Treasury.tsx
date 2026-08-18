import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, Upload } from 'lucide-react'
import { treasuryApi } from '@/api'
import { Button, Input } from '@/components/ui'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { day, money } from '@/lib/format'
import { toast } from '@/store/toast'
import type { CapitalCall, Movement } from '@/types'

/** How strongly each clue identifies the payer. Mirrors `app/core/matching.py`, and the
 *  wording is the point: « the amount alone proves nothing » is the sentence that stops an
 *  operator from attributing a transfer because the figure matched. */
const BASIS_TONE: Record<string, 'good' | 'info' | 'warn' | 'neutral'> = {
  virtual_iban: 'good',
  reference: 'info',
  payer_iban: 'warn',
  amount: 'warn',
  unmatched: 'neutral',
}

export default function Treasury() {
  const { t } = useTranslation()
  const [movements, setMovements] = useState<Movement[] | null>(null)
  const [calls, setCalls] = useState<CapitalCall[] | null>(null)
  const [raw, setRaw] = useState('')
  const [busy, setBusy] = useState(false)
  // ⚠️ NO NATIVE DIALOG. `window.prompt` cannot be styled, cannot show the amount it is
  // about, and on a 200 000 attribution the operator deserves to see what they confirm.
  const [attributing, setAttributing] = useState<Movement | null>(null)

  const load = () => {
    treasuryApi.unattributed().then((r) => setMovements(r.data)).catch(() => setMovements([]))
    treasuryApi.calls().then((r) => setCalls(r.data)).catch(() => setCalls([]))
  }
  useEffect(load, [])

  const importLines = async () => {
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      toast.error(t('treasury.notJson'))
      return
    }
    if (!Array.isArray(parsed)) {
      toast.error(t('treasury.notAList'))
      return
    }
    setBusy(true)
    try {
      const { data } = await treasuryApi.importMovements(parsed as Record<string, unknown>[])
      // ⚠️ A re-import is normal and lines already known are SKIPPED, not duplicated. The
      // count says how many were actually new so the operator is not left guessing.
      toast.success(t('treasury.imported', { count: data.length }))
      setRaw('')
      load()
    } catch {
      /* handled by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title={t('treasury.title')} subtitle={t('treasury.subtitle')} />

      <Card className="p-4 mb-6">
        <h2 className="text-sm font-semibold text-gray-900 mb-1">{t('treasury.importTitle')}</h2>
        <p className="text-xs text-gray-500 mb-3">{t('treasury.importHelp')}</p>
        <textarea
          value={raw}
          onChange={(e) => setRaw(e.target.value)}
          rows={4}
          spellCheck={false}
          placeholder='[{"account_iban":"FR76…","direction":"in","amount":"50000","currency":"EUR","value_date":"2026-03-01"}]'
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <div className="mt-3">
          <Button onClick={importLines} isLoading={busy} disabled={!raw.trim()}>
            <Upload size={15} /> {t('treasury.import')}
          </Button>
        </div>
      </Card>

      <h2 className="text-sm font-semibold text-gray-900 mb-2">{t('treasury.unidentified')}</h2>
      {movements === null ? (
        <Loading label={t('common.loading')} />
      ) : movements.length === 0 ? (
        <Card className="mb-8">
          <EmptyState title={t('dashboard.nothingPending')}>
            {t('dashboard.nothingPendingBody')}
          </EmptyState>
        </Card>
      ) : (
        <div className="mb-8">
          <TableWrap>
            <thead>
              <tr>
                <Th>{t('common.date')}</Th>
                <Th>{t('treasury.label')}</Th>
                <Th>{t('treasury.proposal')}</Th>
                <Th right>{t('common.amount')}</Th>
                <Th right>{t('common.status')}</Th>
              </tr>
            </thead>
            <tbody>
              {movements.map((m) => {
                const basis = m.proposal?.basis ?? 'unmatched'
                return (
                  <tr key={m.id}>
                    <Td className="text-gray-500 whitespace-nowrap">{day(m.value_date)}</Td>
                    <Td>
                      <span className="text-gray-900">{m.counterparty_name || '—'}</span>
                      {m.label && <p className="mt-0.5 text-xs text-gray-500 max-w-xs truncate">{m.label}</p>}
                    </Td>
                    <Td>
                      <Pill tone={BASIS_TONE[basis] ?? 'neutral'}>{t(`treasury.basis.${basis}`)}</Pill>
                      {m.proposal?.third_party_payer && (
                        <span className="ml-1.5">
                          <Pill tone="warn"><AlertTriangle size={11} /> {t('treasury.thirdParty')}</Pill>
                        </span>
                      )}
                      {m.proposal && (
                        <p className="mt-1 text-xs text-gray-500 max-w-md leading-snug">
                          {m.proposal.explanation}
                        </p>
                      )}
                    </Td>
                    <Td right className="font-medium">{money(m.amount, m.currency)}</Td>
                    <Td right>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setAttributing(attributing?.id === m.id ? null : m)}
                      >
                        {t('treasury.impute')}
                      </Button>
                    </Td>
                  </tr>
                )
              })}
            </tbody>
          </TableWrap>

          {attributing && (
            <div className="mt-3">
              <AttributionForm
                movement={attributing}
                onCancel={() => setAttributing(null)}
                onDone={() => {
                  setAttributing(null)
                  load()
                }}
              />
            </div>
          )}

          <div className="mt-3">
            {/* The rule proposes, a human decides, and `attributed_by` records who. */}
            <Notice tone="info" title={t('treasury.ruleProposesTitle')}>
              {t('treasury.ruleProposesBody')}
            </Notice>
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <h2 className="text-sm font-semibold text-gray-900">{t('treasury.calls')}</h2>
        <NewCall onDone={load} />
      </div>
      {calls === null ? (
        <Loading label={t('common.loading')} />
      ) : calls.length === 0 ? (
        <Card>
          <EmptyState title={t('treasury.noCalls')}>{t('treasury.noCallsBody')}</EmptyState>
        </Card>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <Th>{t('common.reference')}</Th>
              <Th>{t('treasury.issuedOn')}</Th>
              <Th>{t('common.dueDate')}</Th>
              <Th right>{t('common.amount')}</Th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr key={c.id}>
                <Td className="font-mono text-xs">{c.reference}</Td>
                <Td className="text-gray-500 whitespace-nowrap">{day(c.called_on)}</Td>
                <Td className="whitespace-nowrap">{day(c.due_on)}</Td>
                <Td right className="font-medium">{money(c.amount, c.currency)}</Td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </>
  )
}

function NewCall({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [subscriptionId, setSubscriptionId] = useState('')
  const [amount, setAmount] = useState('')
  const [dueOn, setDueOn] = useState('')
  const [busy, setBusy] = useState(false)
  const today = new Date().toISOString().slice(0, 10)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await treasuryApi.openCall({
        subscription_id: subscriptionId.trim(),
        amount,
        called_on: today,
        due_on: dueOn,
      })
      toast.success(t('treasury.callIssued'))
      setOpen(false)
      setSubscriptionId('')
      setAmount('')
      setDueOn('')
      onDone()
    } catch {
      /* handled by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
        {t('treasury.newCall')}
      </Button>
    )
  }

  return (
    <Card className="p-4 w-full">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4 items-end">
        <Input
          label={t('treasury.subscription')}
          value={subscriptionId}
          onChange={(e) => setSubscriptionId(e.target.value)}
          required
          hint={t('treasury.callSubscriptionHint')}
        />
        <Input
          label={t('common.amount')}
          type="number"
          min="0"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          required
        />
        <Input
          label={t('common.dueDate')}
          type="date"
          value={dueOn}
          onChange={(e) => setDueOn(e.target.value)}
          required
        />
        <div className="flex gap-2">
          <Button type="submit" isLoading={busy}>{t('treasury.issue')}</Button>
          <Button type="button" variant="ghost" onClick={() => setOpen(false)}>{t('common.cancel')}</Button>
        </div>
      </form>
    </Card>
  )
}

function AttributionForm({
  movement, onCancel, onDone,
}: { movement: Movement; onCancel: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [subscriptionId, setSubscriptionId] = useState('')
  const [amount, setAmount] = useState(movement.amount)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await treasuryApi.attribute(movement.id, {
        subscription_id: subscriptionId.trim(),
        amount,
        third_party_reason: reason.trim() || undefined,
      })
      toast.success(t('treasury.imputed'))
      onDone()
    } catch {
      /* handled by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-4 border-brand-navy/30">
      <p className="text-sm font-semibold text-gray-900">
        {t('treasury.imputeTitle', {
          amount: money(movement.amount, movement.currency),
          date: day(movement.value_date),
        })}
      </p>
      <p className="mt-0.5 mb-3 text-xs text-gray-500">
        {t('treasury.payerIs', { name: movement.counterparty_name || t('treasury.payerUnknown') })}
        {movement.proposal?.third_party_payer && ` ${t('treasury.thirdPartyWarning')}`}
      </p>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4 items-end">
        <Input
          label={t('treasury.subscription')}
          value={subscriptionId}
          onChange={(e) => setSubscriptionId(e.target.value)}
          required
          hint={t('treasury.subscriptionHint')}
        />
        <Input
          label={t('treasury.imputedAmount')}
          type="number"
          min="0"
          step="0.01"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          required
          hint={t('treasury.imputedAmountHint')}
        />
        <Input
          label={t('treasury.thirdPartyReason')}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          hint={t('treasury.thirdPartyReasonHint')}
        />
        <div className="flex gap-2">
          <Button type="submit" isLoading={busy}>{t('common.confirm')}</Button>
          <Button type="button" variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button>
        </div>
      </form>
    </Card>
  )
}

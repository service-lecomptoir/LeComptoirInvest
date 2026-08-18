import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Check, Receipt, X } from 'lucide-react'
import { subscriptionsApi } from '@/api'
import { Button, Input } from '@/components/ui'
import {
  Card, EmptyState, Loading, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { day, money } from '@/lib/format'
import { toast } from '@/store/toast'
import type { SubscriptionRequest } from '@/types'

const STATE_TONE: Record<string, 'warn' | 'good' | 'bad' | 'neutral'> = {
  pending: 'warn',
  accepted: 'good',
  refused: 'bad',
  withdrawn: 'neutral',
}

/**
 * A REQUEST IS NOT AN ENGAGEMENT, and this screen is where the difference becomes an act.
 * Accepting is what creates the commitment; the two rows both survive, because what was
 * asked and what was agreed are different facts and only one of them binds.
 */
export default function Subscriptions() {
  const { t } = useTranslation()
  const [rows, setRows] = useState<SubscriptionRequest[] | null>(null)
  const [refusing, setRefusing] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const load = () =>
    subscriptionsApi.requests().then((r) => setRows(r.data)).catch(() => setRows([]))
  useEffect(() => {
    load()
  }, [])

  const accept = async (id: string) => {
    setBusy(true)
    try {
      await subscriptionsApi.decide(id, { accept: true })
      toast.success(t('subscriptions.accepted'))
      load()
    } catch {
      /* handled by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  const refuse = async (id: string) => {
    if (!reason.trim()) {
      // 🔴 REFUSED HERE TOO, NOT ONLY BY THE SERVER. An investor told « no » with no reason
      // can neither correct anything nor ask for it to be looked at again.
      toast.error(t('subscriptions.reasonRequired'))
      return
    }
    setBusy(true)
    try {
      await subscriptionsApi.decide(id, { accept: false, reason: reason.trim() })
      toast.success(t('subscriptions.refused'))
      setRefusing(null)
      setReason('')
      load()
    } catch {
      /* handled by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <PageHeader title={t('subscriptions.title')} subtitle={t('subscriptions.subtitle')} />

      {rows === null ? (
        <Loading label={t('common.loading')} />
      ) : rows.length === 0 ? (
        <Card>
          <EmptyState title={t('subscriptions.none')} icon={<Receipt size={32} />}>
            {t('subscriptions.noneBody')}
          </EmptyState>
        </Card>
      ) : (
        <>
          <TableWrap>
            <thead>
              <tr>
                <Th>{t('subscriptions.requestedOn')}</Th>
                <Th>{t('subscriptions.instrument')}</Th>
                <Th right>{t('common.amount')}</Th>
                <Th>{t('common.status')}</Th>
                <Th right>{t('common.confirm')}</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <Td className="text-gray-500 whitespace-nowrap">{day(r.requested_on)}</Td>
                  <Td>{t(`subscriptions.instruments.${r.instrument}`, { defaultValue: r.instrument })}</Td>
                  <Td right className="font-medium">{money(r.amount, r.currency)}</Td>
                  <Td>
                    <Pill tone={STATE_TONE[r.status] ?? 'neutral'}>
                      {t(`subscriptions.requestState.${r.status}`, { defaultValue: r.status })}
                    </Pill>
                    {r.decision_reason && (
                      <p className="mt-1 text-xs text-gray-500 max-w-sm">{r.decision_reason}</p>
                    )}
                  </Td>
                  <Td right>
                    {r.status === 'pending' && (
                      <div className="inline-flex gap-2">
                        <Button size="sm" onClick={() => accept(r.id)} isLoading={busy}>
                          <Check size={14} /> {t('subscriptions.accept')}
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => setRefusing(refusing === r.id ? null : r.id)}
                        >
                          <X size={14} /> {t('subscriptions.refuse')}
                        </Button>
                      </div>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>

          {refusing && (
            <Card className="mt-3 p-4 border-red-200">
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  refuse(refusing)
                }}
                className="grid gap-3 sm:grid-cols-[1fr_auto] items-end"
              >
                <Input
                  label={t('subscriptions.reason')}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  required
                  hint={t('subscriptions.reasonRequired')}
                />
                <div className="flex gap-2">
                  <Button type="submit" variant="danger" isLoading={busy}>
                    {t('subscriptions.refuse')}
                  </Button>
                  <Button type="button" variant="ghost" onClick={() => setRefusing(null)}>
                    {t('common.cancel')}
                  </Button>
                </div>
              </form>
            </Card>
          )}
        </>
      )}
    </>
  )
}

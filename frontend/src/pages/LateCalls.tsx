import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AlarmClock, Mail, MailWarning } from 'lucide-react'
import { treasuryApi } from '@/api'
import { NoticeDialog } from '@/components/NoticeDialog'
import { Button, Input } from '@/components/ui'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { money, day } from '@/lib/format'
import type { LateCall } from '@/types'

/**
 * Capital calls past their due date and still short.
 *
 * 🔴 THE SCREEN'S JOB IS TO KEEP TWO THINGS APART that a plain « overdue » list would merge.
 * An investor who has paid most of a call is not an investor who has paid nothing, and a
 * call the fund NEVER SENT is not a late investor at all — it is the fund's own omission.
 * Chasing either of them on the strength of one figure writes a letter that is wrong in the
 * way an investor does not forget.
 */
export default function LateCalls() {
  const { t } = useTranslation()
  const today = new Date().toISOString().slice(0, 10)
  const [asOf, setAsOf] = useState(today)
  const [calls, setCalls] = useState<LateCall[] | null>(null)
  /** 🔴 THE ROW THAT SAID « JAMAIS NOTIFIÉ » NAMED THE FUND'S OWN OMISSION AND OFFERED
   *  NOTHING TO DO ABOUT IT. A screen that reports a problem nobody can act on from it is a
   *  screen people learn to scroll past, and this is the row that most needed acting on. */
  const [writingTo, setWritingTo] = useState<string | null>(null)

  useEffect(() => {
    if (!asOf) return
    setCalls(null)
    treasuryApi
      .lateCalls(asOf)
      .then((r) => setCalls(r.data))
      .catch(() => setCalls([]))
  }, [asOf])

  const unsent = (calls ?? []).filter((c) => c.never_notified)

  return (
    <>
      <PageHeader
        title={t('lateCalls.title')}
        subtitle={t('lateCalls.subtitle')}
        actions={
          <div className="min-w-[11rem]">
            <Input
              label={t('lateCalls.asOf')}
              type="date"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
            />
          </div>
        }
      />

      {unsent.length > 0 && (
        <div className="mb-5">
          <Notice tone="bad" title={t('lateCalls.unsentTitle', { count: unsent.length })}>
            {t('lateCalls.unsentHint')}
          </Notice>
        </div>
      )}

      {calls === null ? (
        <Loading label={t('common.loading')} />
      ) : calls.length === 0 ? (
        <Card>
          <EmptyState title={t('lateCalls.none')} icon={<AlarmClock size={28} />}>
            {t('lateCalls.noneHint')}
          </EmptyState>
        </Card>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <Th>{t('lateCalls.reference')}</Th>
              <Th>{t('common.investor')}</Th>
              <Th>{t('lateCalls.dueOn')}</Th>
              <Th right>{t('lateCalls.called')}</Th>
              <Th right>{t('lateCalls.received')}</Th>
              <Th right>{t('lateCalls.outstanding')}</Th>
              <Th right>{t('lateCalls.lateInterest')}</Th>
              <Th>{t('lateCalls.reminder')}</Th>
              <Th>{t('common.actions')}</Th>
            </tr>
          </thead>
          <tbody>
            {calls.map((c) => (
              <tr key={c.call_id}>
                <Td className="font-mono text-[13px]">{c.reference}</Td>
                <Td>{c.investor_name}</Td>
                <Td>
                  {day(c.due_on)}
                  <span className="ml-1.5 text-xs text-gray-500">
                    {t('lateCalls.daysLate', { count: c.days_late })}
                  </span>
                </Td>
                <Td right>{money(c.called, c.currency)}</Td>
                {/* ⚠️ WHAT ARRIVED IS SHOWN BESIDE WHAT WAS ASKED. Partial payment is the
                    norm on large sums, and a reminder written off the called amount duns
                    somebody who paid ninety per cent of it. */}
                <Td right className={Number(c.received) > 0 ? 'text-emerald-700' : 'text-gray-400'}>
                  {money(c.received, c.currency)}
                </Td>
                <Td right className="font-medium">{money(c.outstanding, c.currency)}</Td>
                <Td right className={Number(c.late_interest) > 0 ? 'text-amber-700' : 'text-gray-400'}>
                  {money(c.late_interest, c.currency)}
                </Td>
                <Td>
                  {c.never_notified ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-red-700">
                      <MailWarning size={14} /> {t('lateCalls.neverNotified')}
                    </span>
                  ) : c.reminder_due ? (
                    <Pill tone="warn">{t('lateCalls.reminderDue')}</Pill>
                  ) : (
                    <span className="text-xs text-gray-500">{c.reminder_blocked_reason}</span>
                  )}
                </Td>
                <Td>
                  <Button
                    size="sm"
                    variant="secondary"
                    leftIcon={<Mail size={14} />}
                    onClick={() => setWritingTo(c.call_id)}
                  >
                    {c.never_notified ? t('notice.writeFirst') : t('notice.writeReminder')}
                  </Button>
                </Td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}

      {writingTo && (
        <NoticeDialog
          callId={writingTo}
          asOf={asOf}
          onClose={() => setWritingTo(null)}
          onSent={() => {
            setWritingTo(null)
            // The call has just stopped being « never notified ». Reloading is what makes
            // the row say so, instead of showing a state the click already changed.
            setCalls(null)
            treasuryApi
              .lateCalls(asOf)
              .then((r) => setCalls(r.data))
              .catch(() => setCalls([]))
          }}
        />
      )}
    </>
  )
}

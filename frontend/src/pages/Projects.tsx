import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Building2, Plus } from 'lucide-react'
import { projectsApi } from '@/api'
import { Button, Input, Select } from '@/components/ui'
import { useAuthStore } from '@/store/authStore'
import {
  Card, EmptyState, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { money, number } from '@/lib/format'
import { toast } from '@/store/toast'
import type { Project } from '@/types'

/** ⚠️ « closed » and « written_off » are not the same news, and the investor is owed the
 *  difference in plain words rather than one green pill for both. */
const STATUS_TONE: Record<string, 'neutral' | 'info' | 'good' | 'bad'> = {
  study: 'neutral',
  active: 'info',
  closed: 'good',
  written_off: 'bad',
}

const CURRENCIES = ['EUR', 'XOF', 'USD', 'GBP', 'MAD', 'XAF']

export default function Projects() {
  const { t } = useTranslation()
  const seesWholeFund = useAuthStore((s) => s.seesWholeFund)
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [creating, setCreating] = useState(false)
  const [acting, setActing] = useState<{ project: Project; what: Action } | null>(null)

  const load = () => projectsApi.list().then((r) => setProjects(r.data)).catch(() => setProjects([]))
  useEffect(() => {
    load()
  }, [])

  return (
    <>
      <PageHeader
        title={t('projects.title')}
        subtitle={t('projects.subtitle')}
        actions={
          seesWholeFund && !creating ? (
            <Button size="sm" onClick={() => setCreating(true)}>
              <Plus size={15} /> {t('projects.new')}
            </Button>
          ) : undefined
        }
      />

      {creating && (
        <div className="mb-6">
          <NewProject onCancel={() => setCreating(false)} onDone={() => { setCreating(false); load() }} />
        </div>
      )}

      {projects === null ? (
        <Loading label={t('common.loading')} />
      ) : projects.length === 0 ? (
        <Card>
          <EmptyState title={t('projects.none')} icon={<Building2 size={32} />}>
            {t('projects.noneBody')}
          </EmptyState>
        </Card>
      ) : (
        <>
          <TableWrap>
            <thead>
              <tr>
                <Th>{t('common.project')}</Th>
                <Th>{t('common.status')}</Th>
                <Th right>{t('projects.deployed')}</Th>
                <Th right>{t('projects.capitalReturned')}</Th>
                <Th right>{t('common.income')}</Th>
                <Th right>{t('projects.stillIn')}</Th>
                <Th right>{t('projects.multiple')}</Th>
                {/* ⚠️ NOT `common.status`: the state column already exists three
                    columns earlier, and two identical headers in the same table
                    make reading impossible -- seen on screen. */}
                {seesWholeFund && <Th right>{t('common.actions')}</Th>}
              </tr>
            </thead>
            <tbody>
              {projects.map((p) => (
                <tr key={p.id}>
                  <Td className="text-gray-900">{p.name}</Td>
                  <Td>
                    <Pill tone={STATUS_TONE[p.status] ?? 'neutral'}>
                      {t(`projects.status.${p.status}`, { defaultValue: p.status })}
                    </Pill>
                  </Td>
                  <Td right>{money(p.deployed, p.currency)}</Td>
                  <Td right>{money(p.capital_returned, p.currency)}</Td>
                  {/* The gain is the income and only the income: a project that returned
                      exactly what it took has earned nothing. */}
                  <Td right className={Number(p.income_returned) > 0 ? 'text-emerald-700 font-medium' : ''}>
                    {money(p.income_returned, p.currency)}
                  </Td>
                  <Td right className={Number(p.outstanding) < 0 ? 'text-red-700 font-medium' : ''}>
                    {money(p.outstanding, p.currency)}
                  </Td>
                  <Td right className="font-medium">
                    {p.multiple === null ? <span className="text-gray-400">-</span> : `${number(p.multiple)}x`}
                  </Td>
                  {seesWholeFund && (
                    <Td right>
                      <div className="inline-flex gap-1.5">
                        {(['deploy', 'return', 'value', 'status'] as Action[]).map((what) => (
                          <Button
                            key={what}
                            size="sm"
                            variant="secondary"
                            onClick={() =>
                              setActing(
                                acting?.project.id === p.id && acting.what === what
                                  ? null
                                  : { project: p, what },
                              )
                            }
                          >
                            {t(
                              what === 'deploy'
                                ? 'project.deploy'
                                : what === 'return'
                                  ? 'project.recordReturn'
                                  : what === 'value'
                                    ? 'project.value'
                                    : 'project.changeStatus',
                            )}
                          </Button>
                        ))}
                      </div>
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </TableWrap>
          {acting && (
            <div className="mt-3">
              <ProjectAction
                project={acting.project}
                what={acting.what}
                onCancel={() => setActing(null)}
                onDone={() => {
                  setActing(null)
                  load()
                }}
              />
            </div>
          )}

          {projects.some((p) => Number(p.outstanding) < 0) && (
            <div className="mt-3">
              <Notice tone="warn" title={t('projects.overReturnedTitle')}>
                {t('projects.overReturnedBody')}
              </Notice>
            </div>
          )}
        </>
      )}
    </>
  )
}

function NewProject({ onCancel, onDone }: { onCancel: () => void; onDone: () => void }) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [currency, setCurrency] = useState('EUR')
  const [target, setTarget] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      await projectsApi.create({
        name: name.trim(),
        currency,
        target_amount: target ? target : null,
      })
      toast.success(t('projects.created'))
      onDone()
    } catch {
      /* handled by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card className="p-4">
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4 items-end">
        <Input label={t('projects.name')} value={name} onChange={(e) => setName(e.target.value)} required />
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">{t('common.currency')}</label>
          <Select
            value={currency}
            onChange={setCurrency}
            options={CURRENCIES.map((c) => ({ value: c, label: c }))}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
          />
        </div>
        <Input
          label={t('projects.target')}
          type="number"
          min="0"
          step="0.01"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        />
        <div className="flex gap-2">
          <Button type="submit" isLoading={busy}>{t('common.create')}</Button>
          <Button type="button" variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button>
        </div>
      </form>
      <p className="mt-3 text-xs text-gray-500 max-w-3xl leading-relaxed">{t('projects.targetHint')}</p>
    </Card>
  )
}


type Action = 'deploy' | 'return' | 'status' | 'value'

/**
 * The three gestures that make a project live, and that had no screen at all: the money
 * left, came back and the state changed -- in the API only. A project that never moves
 * makes a dashboard perfectly consistent and perfectly wrong.
 *
 * 🔴 EVERY AMOUNT IS CHARGED TO A BANK MOVEMENT, never to a free entry. That is the rule of
 * the product: a project whose performance is typed in by hand returns what its manager
 * believes, and believing is precisely what an investor pays not to have to do.
 *
 * 🔴 AND THE RETURN IS SPLIT INTO TWO FIELDS, capital and income. A single figure would let
 * one present as a performance a project that has merely given back the money entrusted to
 * it -- the oldest flattering mistake of the trade.
 */
function ProjectAction({
  project, what, onCancel, onDone,
}: {
  project: Project
  what: Action
  onCancel: () => void
  onDone: () => void
}) {
  const { t } = useTranslation()
  const [movementId, setMovementId] = useState('')
  const [amount, setAmount] = useState('')
  const [capital, setCapital] = useState('')
  const [income, setIncome] = useState('')
  const [note, setNote] = useState('')
  const [status, setStatus] = useState(project.status)
  const [closedOn, setClosedOn] = useState('')
  // 🔴 THE CLOSING DATE, NOT THE DATE OF ENTRY. A valuation of March recorded in May
  // stays a figure of March; dating it from the day it is typed would shift every
  // quarterly report by the delay of whoever writes it.
  const [valuedOn, setValuedOn] = useState('')
  const [valuation, setValuation] = useState('')
  const [basis, setBasis] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    try {
      if (what === 'deploy') {
        await projectsApi.deploy(project.id, {
          bank_movement_id: movementId.trim(),
          amount,
          note: note.trim() || undefined,
        })
        toast.success(t('project.deployed'))
      } else if (what === 'return') {
        await projectsApi.recordReturn(project.id, {
          bank_movement_id: movementId.trim(),
          capital_amount: capital || '0',
          income_amount: income || '0',
          note: note.trim() || undefined,
        })
        toast.success(t('project.returned'))
      } else if (what === 'value') {
        await projectsApi.recordValuation(project.id, {
          valued_on: valuedOn,
          amount: valuation,
          basis: basis.trim() || undefined,
        })
        toast.success(t('project.valued'))
      } else {
        await projectsApi.setStatus(project.id, {
          status,
          closed_on: closedOn || undefined,
        })
        toast.success(t('project.statusChanged'))
      }
      onDone()
    } catch {
      /* the message of the server is already shown by the interceptor */
    } finally {
      setBusy(false)
    }
  }

  const title =
    what === 'deploy'
      ? t('project.deployTitle', { name: project.name })
      : what === 'return'
        ? t('project.returnTitle', { name: project.name })
        : what === 'value'
          ? t('project.valueTitle', { name: project.name })
          : t('project.changeStatus')

  return (
    <Card className="p-4 border-brand-navy/30">
      <p className="text-sm font-semibold text-gray-900">{title}</p>
      {what === 'value' && (
        <p className="mt-0.5 mb-3 text-xs text-gray-500 max-w-2xl">{t('project.valueHint')}</p>
      )}
      {what === 'return' && (
        <p className="mt-0.5 mb-3 text-xs text-gray-500 max-w-2xl">{t('project.splitRequired')}</p>
      )}
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-4 items-end mt-2">
        {/* ⚠️ A VALUATION IS CHARGED TO NO BANK MOVEMENT. It is a judgement,
            not a flow: demanding a transfer reference here would force one to invent one,
            and the rule « chaque montant vient de la banque » would lose its meaning where
            it really counts, that is to say on the money. */}
        {what !== 'status' && what !== 'value' && (
          <Input
            label={t('project.movement')}
            value={movementId}
            onChange={(e) => setMovementId(e.target.value)}
            required
          />
        )}

        {what === 'value' && (
          <>
            <Input
              label={t('project.valuedOn')}
              type="date"
              value={valuedOn}
              onChange={(e) => setValuedOn(e.target.value)}
              required
            />
            <Input
              label={t('project.valuedAmount')}
              type="number"
              min="0"
              step="0.01"
              value={valuation}
              onChange={(e) => setValuation(e.target.value)}
              required
            />
            <Input
              label={t('project.basis')}
              value={basis}
              onChange={(e) => setBasis(e.target.value)}
            />
          </>
        )}

        {what === 'deploy' && (
          <Input
            label={t('common.amount')}
            type="number"
            min="0"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        )}

        {what === 'return' && (
          <>
            <Input
              label={t('project.capitalBack')}
              type="number"
              min="0"
              step="0.01"
              value={capital}
              onChange={(e) => setCapital(e.target.value)}
              required
            />
            <Input
              label={t('project.incomeBack')}
              type="number"
              min="0"
              step="0.01"
              value={income}
              onChange={(e) => setIncome(e.target.value)}
              required
            />
          </>
        )}

        {what === 'status' && (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {t('common.status')}
              </label>
              <Select
                value={status}
                onChange={setStatus}
                options={['study', 'active', 'closed', 'written_off'].map((v) => ({
                  value: v,
                  label: t(`projects.status.${v}`),
                }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
              />
            </div>
            <Input
              label={t('project.closedOn')}
              type="date"
              value={closedOn}
              onChange={(e) => setClosedOn(e.target.value)}
            />
          </>
        )}

        {what !== 'status' && (
          <Input label={t('project.note')} value={note} onChange={(e) => setNote(e.target.value)} />
        )}

        <div className="flex gap-2">
          <Button type="submit" isLoading={busy}>{t('common.confirm')}</Button>
          <Button type="button" variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button>
        </div>
      </form>
      <p className="mt-3 text-xs text-gray-500 max-w-3xl leading-relaxed">{what === 'deploy' ? t('project.movementOut') : t('project.movementIn')}</p>
    </Card>
  )
}

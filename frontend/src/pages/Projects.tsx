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
                    {p.multiple === null ? <span className="text-gray-400">—</span> : `${number(p.multiple)}x`}
                  </Td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
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
          hint={t('projects.targetHint')}
        />
        <div className="flex gap-2">
          <Button type="submit" isLoading={busy}>{t('common.create')}</Button>
          <Button type="button" variant="ghost" onClick={onCancel}>{t('common.cancel')}</Button>
        </div>
      </form>
    </Card>
  )
}

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { AlertTriangle, ArrowRight, Building2, Wallet } from 'lucide-react'
import { distributionsApi, projectsApi, treasuryApi } from '@/api'
import {
  Card, EmptyState, Kpi, KpiRow, Loading, Notice, PageHeader, Pill, TableWrap, Td, Th,
} from '@/components/common/Primitives'
import { day, money, number } from '@/lib/format'
import type { Movement, Project } from '@/types'

interface CurrencyBlock {
  currency: string
  cash: string
  owed: string
  unmeasurable: string[]
}

export default function Dashboard() {
  const { t } = useTranslation()
  const [blocks, setBlocks] = useState<CurrencyBlock[] | null>(null)
  const [unattributed, setUnattributed] = useState<Movement[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const today = new Date().toISOString().slice(0, 10)

  useEffect(() => {
    let alive = true
    const load = async () => {
      const [balance, pending, projectList] = await Promise.all([
        treasuryApi.balance(),
        treasuryApi.unattributed(),
        projectsApi.list(),
      ])
      if (!alive) return
      setUnattributed(pending.data)
      setProjects(projectList.data)

      // 🔴 THE DEBT IS FETCHED PER CURRENCY, BESIDE THE CASH. A balance shown on its own
      // is the figure that gets distributed, and the fund would be distributing money it
      // already owes its lenders.
      const currencies = Object.keys(balance.data)
      const debts = await Promise.all(
        currencies.map((c) => distributionsApi.debt(c, today).then((r) => r.data)),
      )
      if (!alive) return
      setBlocks(
        currencies.map((currency, i) => ({
          currency,
          cash: balance.data[currency],
          owed: debts[i].owed_to_lenders,
          unmeasurable: debts[i].unmeasurable,
        })),
      )
    }
    load().catch(() => alive && setBlocks([]))
    return () => {
      alive = false
    }
  }, [today])

  if (blocks === null) return <Loading label={t('common.loading')} />

  const anyUnmeasurable = blocks.flatMap((b) => b.unmeasurable)

  return (
    <>
      <PageHeader title={t('dashboard.title')} subtitle={t('dashboard.subtitle')} />

      {anyUnmeasurable.length > 0 && (
        <div className="mb-6">
          <Notice tone="bad" title={t('dashboard.unmeasurableTitle')}>
            <p>{t('dashboard.unmeasurableBody')}</p>
            <ul className="mt-2 list-disc pl-5 space-y-0.5">
              {anyUnmeasurable.map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          </Notice>
        </div>
      )}

      {blocks.length === 0 ? (
        <Card className="mb-6">
          <EmptyState title={t('dashboard.noMovements')} icon={<Wallet size={32} />}>
            {t('dashboard.noMovementsBody')}
          </EmptyState>
        </Card>
      ) : (
        blocks.map((block) => {
          const cash = Number(block.cash)
          const owed = Number(block.owed)
          const free = cash - owed
          return (
            <div key={block.currency} className="mb-6">
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
                {t('dashboard.positionIn', { currency: block.currency })}
              </p>
              <KpiRow>
                <Kpi
                  label={t('dashboard.cash')}
                  value={money(cash, block.currency)}
                  hint={t('dashboard.cashHint')}
                />
                <Kpi
                  label={t('dashboard.owed')}
                  value={money(owed, block.currency)}
                  tone={owed > 0 ? 'warn' : 'neutral'}
                  hint={t('dashboard.owedHint')}
                />
                <Kpi
                  label={t('dashboard.free')}
                  value={money(free, block.currency)}
                  tone={free < 0 ? 'bad' : 'good'}
                  hint={free < 0 ? t('dashboard.freeNegative') : t('dashboard.freeHint')}
                />
                <Kpi
                  label={t('dashboard.toImpute')}
                  value={number(unattributed.filter((m) => m.currency === block.currency).length, 0)}
                  tone={unattributed.some((m) => m.currency === block.currency) ? 'warn' : 'neutral'}
                  hint={t('dashboard.toImputeHint')}
                />
              </KpiRow>
            </div>
          )
        })
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-gray-900">{t('dashboard.unidentified')}</h2>
            <Link to="/treasury" className="text-xs text-brand-navy hover:underline inline-flex items-center gap-1">
              {t('dashboard.goTreasury')} <ArrowRight size={13} />
            </Link>
          </div>
          {unattributed.length === 0 ? (
            <Card>
              <EmptyState title={t('dashboard.nothingPending')}>
                {t('dashboard.nothingPendingBody')}
              </EmptyState>
            </Card>
          ) : (
            <TableWrap>
              <thead>
                <tr>
                  <Th>{t('common.date')}</Th>
                  <Th>{t('dashboard.payer')}</Th>
                  <Th right>{t('common.amount')}</Th>
                </tr>
              </thead>
              <tbody>
                {unattributed.slice(0, 6).map((m) => (
                  <tr key={m.id}>
                    <Td className="text-gray-500 whitespace-nowrap">{day(m.value_date)}</Td>
                    <Td>
                      <span className="text-gray-900">{m.counterparty_name || '—'}</span>
                      {m.proposal?.third_party_payer && (
                        <span className="ml-2">
                          <Pill tone="warn">
                            <AlertTriangle size={11} /> {t('treasury.thirdParty')}
                          </Pill>
                        </span>
                      )}
                      {m.proposal && (
                        <p className="mt-0.5 text-xs text-gray-500">{m.proposal.explanation}</p>
                      )}
                    </Td>
                    <Td right className="font-medium">{money(m.amount, m.currency)}</Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </section>

        <section>
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-semibold text-gray-900">{t('nav.projects')}</h2>
            <Link to="/projects" className="text-xs text-brand-navy hover:underline inline-flex items-center gap-1">
              {t('dashboard.allProjects')} <ArrowRight size={13} />
            </Link>
          </div>
          {projects.length === 0 ? (
            <Card>
              <EmptyState title={t('dashboard.noProjects')} icon={<Building2 size={32} />}>
                {t('dashboard.noProjectsBody')}
              </EmptyState>
            </Card>
          ) : (
            <TableWrap>
              <thead>
                <tr>
                  <Th>{t('common.project')}</Th>
                  <Th right>{t('projects.deployed')}</Th>
                  <Th right>{t('projects.multiple')}</Th>
                </tr>
              </thead>
              <tbody>
                {projects.slice(0, 6).map((p) => (
                  <tr key={p.id}>
                    <Td>
                      <span className="text-gray-900">{p.name}</span>
                      <p className="mt-0.5 text-xs text-gray-500">{t(`projects.status.${p.status}`)}</p>
                    </Td>
                    <Td right>{money(p.deployed, p.currency)}</Td>
                    <Td right className="font-medium">
                      {/* None rather than 0,00x: a project that has not started has no
                          multiple, and « 0,00x » reads as one that lost everything. */}
                      {p.multiple === null ? (
                        <span className="text-gray-400">—</span>
                      ) : (
                        `${number(p.multiple)}x`
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </section>
      </div>
    </>
  )
}

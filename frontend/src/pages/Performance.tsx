import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { TrendingUp } from 'lucide-react'
import { performanceApi } from '@/api'
import { Select } from '@/components/ui'
import {
  Card, EmptyState, Kpi, KpiRow, Loading, Notice, PageHeader,
} from '@/components/common/Primitives'
import { money, percent } from '@/lib/format'
import type { PerformanceBlock } from '@/types'

/**
 * How the fund actually performed, one block per currency.
 *
 * 🔴 THE SCREEN'S JOB IS TO CARRY THE MISSING HALF. Three of the four standard measures
 * need a valuation of what is still held, and this product values nothing. A dashboard that
 * printed « TVPI 0.30 » where the answer is « unknown » would under-state every open fund,
 * and an under-stated return is the error nobody ever disputes.
 *
 * So a figure that could not be computed is shown as « - » with the reason in plain sight,
 * never as a zero.
 */
export default function Performance() {
  const { t } = useTranslation()
  const thisYear = new Date().getFullYear()
  const [asOf, setAsOf] = useState(`${thisYear}-12-31`)
  const [blocks, setBlocks] = useState<PerformanceBlock[] | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    performanceApi
      .get(asOf)
      .then((r) => setBlocks(r.data))
      .catch(() => setBlocks(null))
      .finally(() => setLoading(false))
  }, [asOf])

  /** A ratio that could not be computed reads as a dash, never as zero.
   *  The API sends decimals as strings, so exactness survives the wire: they are turned
   *  into numbers here, at the only place where the value is being displayed. */
  const ratio = (value: string | null | undefined) =>
    value == null ? '-' : `${Number(value).toFixed(2)}x`

  const years = Array.from({ length: 6 }, (_, i) => thisYear - i)

  return (
    <>
      <PageHeader
        title={t('performance.title')}
        subtitle={t('performance.subtitle')}
        actions={
          <div className="min-w-[10rem]">
            <Select
              value={asOf}
              onChange={setAsOf}
              options={years.map((y) => ({ value: `${y}-12-31`, label: `31/12/${y}` }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
              aria-label={t('performance.asOf')}
            />
          </div>
        }
      />

      {loading ? (
        <Loading label={t('common.loading')} />
      ) : !blocks || blocks.length === 0 ? (
        <Card>
          <EmptyState title={t('performance.nothing')} icon={<TrendingUp size={28} />}>
            {t('performance.nothingHint')}
          </EmptyState>
        </Card>
      ) : (
        <div className="space-y-8">
          {blocks.map((block) => (
            <section key={block.currency}>
              <h2 className="mb-3 text-sm font-semibold text-gray-900">{block.currency}</h2>

              <KpiRow>
                <Kpi
                  label={t('performance.paidIn')}
                  value={money(block.paid_in, block.currency)}
                />
                <Kpi
                  label={t('performance.distributed')}
                  value={money(block.distributed, block.currency)}
                />
                <Kpi
                  label="DPI"
                  value={ratio(block.dpi)}
                  hint={t('performance.dpiHint')}
                />
                <Kpi
                  label="TVPI"
                  value={ratio(block.tvpi)}
                  hint={t('performance.tvpiHint')}
                  tone={block.tvpi == null ? 'warn' : 'neutral'}
                />
              </KpiRow>

              <KpiRow>
                <Kpi
                  label={
                    block.irr_is_realised_only
                      ? t('performance.irrRealised')
                      : t('performance.irr')
                  }
                  value={block.irr == null ? '-' : percent(Number(block.irr))}
                  hint={
                    block.irr_is_realised_only
                      ? t('performance.irrRealisedHint')
                      : undefined
                  }
                  tone={
                    block.irr == null
                      ? 'warn'
                      : Number(block.irr) < 0
                        ? 'bad'
                        : 'good'
                  }
                />
                <Kpi
                  label="RVPI"
                  value={ratio(block.rvpi)}
                  hint={t('performance.rvpiHint')}
                  tone={block.rvpi == null ? 'warn' : 'neutral'}
                />
                <Kpi
                  label={t('performance.residual')}
                  value={
                    block.residual_value == null
                      ? '-'
                      : money(block.residual_value, block.currency)
                  }
                  hint={t('performance.residualHint')}
                  tone={block.residual_value == null ? 'warn' : 'neutral'}
                />
              </KpiRow>

              {block.unavailable_reason && (
                <Notice tone="warn" title={t('performance.incomplete')}>
                  {block.unavailable_reason}
                </Notice>
              )}
            </section>
          ))}
        </div>
      )}
    </>
  )
}

import type { ReactNode } from 'react'
import clsx from 'clsx'
import { Spinner } from '@/components/ui'

/**
 * The building blocks every screen of a fund console is made of.
 *
 * THE ONE TYPOGRAPHIC RULE THAT MATTERS HERE: figures are right-aligned and set in
 * TABULAR FIGURES. A column of amounts whose digits do not line up cannot be scanned —
 * the reader has to parse each number instead of seeing the shape of the column — and
 * comparing amounts at a glance is the entire job of these screens.
 */

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={clsx('bg-white border border-gray-200 rounded-xl', className)}>{children}</div>
  )
}

export function PageHeader({
  title, subtitle, actions,
}: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="text-xl font-semibold text-gray-900 tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-gray-500 max-w-2xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

/** A headline figure. `hint` carries the sentence that stops it being misread. */
export function Kpi({
  label, value, hint, tone = 'neutral',
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: 'neutral' | 'good' | 'warn' | 'bad'
}) {
  const toneCls = {
    neutral: 'text-gray-900',
    good: 'text-emerald-700',
    warn: 'text-amber-700',
    bad: 'text-red-700',
  }[tone]
  return (
    <Card className="px-4 py-3.5">
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500">{label}</p>
      <p className={clsx('mt-1.5 text-xl font-semibold tabular-nums tracking-tight', toneCls)}>{value}</p>
      {hint && <p className="mt-1 text-xs text-gray-500 leading-snug">{hint}</p>}
    </Card>
  )
}

export function KpiRow({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 mb-6">{children}</div>
}

/** A table that scrolls sideways INSIDE its card rather than pushing the page wide. */
export function TableWrap({ children }: { children: ReactNode }) {
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">{children}</table>
      </div>
    </Card>
  )
}

export function Th({
  children, right, className,
}: { children: ReactNode; right?: boolean; className?: string }) {
  return (
    <th
      className={clsx(
        'px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-gray-500 bg-gray-50 border-b border-gray-200 whitespace-nowrap',
        right ? 'text-right' : 'text-left',
        className,
      )}
    >
      {children}
    </th>
  )
}

export function Td({
  children, right, className,
}: { children: ReactNode; right?: boolean; className?: string }) {
  return (
    <td
      className={clsx(
        'px-4 py-3 border-b border-gray-100 align-middle',
        right && 'text-right tabular-nums',
        className,
      )}
    >
      {children}
    </td>
  )
}

const pillCls: Record<string, string> = {
  neutral: 'bg-gray-100 text-gray-700 ring-gray-200',
  good: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  warn: 'bg-amber-50 text-amber-800 ring-amber-200',
  bad: 'bg-red-50 text-red-700 ring-red-200',
  info: 'bg-sky-50 text-sky-700 ring-sky-200',
}

export function Pill({
  tone = 'neutral', children,
}: { tone?: keyof typeof pillCls; children: ReactNode }) {
  return (
    <span className={clsx('inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ring-1 ring-inset', pillCls[tone])}>
      {children}
    </span>
  )
}

/** Shown instead of an empty table. Says what to do, never just « aucune donnée ». */
export function EmptyState({
  title, children, icon,
}: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="px-6 py-12 text-center">
      {icon && <div className="mx-auto mb-3 text-gray-300">{icon}</div>}
      <p className="text-sm font-medium text-gray-700">{title}</p>
      {children && <p className="mt-1 text-sm text-gray-500 max-w-md mx-auto">{children}</p>}
    </div>
  )
}

export function Loading({ label = 'Chargement' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-12 text-sm text-gray-500">
      <Spinner size={16} /> {label}
    </div>
  )
}

/**
 * A refusal the user must read, in place, not as a toast that vanishes.
 *
 * 🔴 THE REASONS THIS PRODUCT REFUSES THINGS ARE THE PRODUCT. « The lenders are still
 * owed 15 000 € » is not an error message, it is the answer. It stays on screen.
 */
export function Notice({
  tone = 'warn', title, children,
}: { tone?: 'warn' | 'bad' | 'info'; title: ReactNode; children?: ReactNode }) {
  const cls = {
    warn: 'bg-amber-50 border-amber-200 text-amber-900',
    bad: 'bg-red-50 border-red-200 text-red-900',
    info: 'bg-sky-50 border-sky-200 text-sky-900',
  }[tone]
  return (
    <div className={clsx('border rounded-xl px-4 py-3', cls)}>
      <p className="text-sm font-semibold">{title}</p>
      {children && <div className="mt-1 text-sm leading-relaxed">{children}</div>}
    </div>
  )
}

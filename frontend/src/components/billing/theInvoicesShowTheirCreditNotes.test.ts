import { describe, expect, it } from 'vitest'
import PAGE from '../../pages/Billing.tsx?raw'
import API from '../../api/index.ts?raw'

const LOCALES = import.meta.glob<{ default: Record<string, unknown> }>('../../i18n/locales/*.json', { eager: true })

/**
 * The owner, 6 Nov 2026: « les avoirs visibles dans "Mon abonnement" des produits ».
 * Each invoice of « Mon abonnement » shows its credit notes, read by the shared
 * `invoiceCredits.ts`; and its period and amount are read from what Alice sends.
 */

const KEYS = [
  'billing.creditPartial',
  'billing.creditTotal',
  'billing.creditNotes',
  'billing.creditNote',
  'billing.creditNoteReason',
  'billing.creditNoteDownload',
  'billing.creditNoteUnavailable',
]

const valueAt = (catalogue: unknown, key: string): unknown =>
  key.split('.').reduce<unknown>((node, part) => (node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined), catalogue)

describe('the invoices of « Mon abonnement »', () => {
  it('read their credit notes through the shared file, with both badges', () => {
    expect(PAGE).toContain("from '@/components/billing/invoiceCredits'")
    expect(PAGE).toContain('creditsOf(invoice)')
    expect(PAGE).toContain('nothingLeftToPay(credits)')
    expect(PAGE).toContain("t('billing.creditPartial')")
    expect(PAGE).toContain("t('billing.creditTotal')")
  })

  it('download a credit note through the authenticated client, never a native box', () => {
    expect(API).toContain('creditNotePdfUrl: (id: string) => `/billing/invoices/credit-notes/${id}/pdf`')
    expect(PAGE).toContain('billingApi.creditNotePdfUrl(note.id)')
    expect(PAGE).toContain("toast.error(t('billing.creditNoteUnavailable'))")
    expect(PAGE).not.toMatch(/\b(alert|confirm|prompt)\(/)
  })

  it('read the period and the amount Alice sends, not fields she never sent', () => {
    expect(PAGE).toContain('period_month')
    expect(PAGE).toContain('period_year')
    expect(PAGE).toContain('amount_ttc')
    expect(PAGE).not.toContain('money(invoice.amount, currency)')
    expect(PAGE).not.toContain('{invoice.period || day(invoice.issued_at)}')
  })

  it('find every key they use in every language', () => {
    const catalogues = Object.entries(LOCALES)
    expect(catalogues.length).toBeGreaterThan(1)
    for (const key of KEYS) {
      expect(PAGE).toContain(`'${key}'`)
      for (const [file, catalogue] of catalogues) {
        expect(typeof valueAt(catalogue.default, key), `${key} in ${file}`).toBe('string')
      }
    }
  })
})

import { describe, expect, it } from 'vitest'
import PAGE from './Billing.tsx?raw'
import BANNER from '../components/layout/SubscriptionBanner.tsx?raw'

const LOCALES = import.meta.glob<{ default: Record<string, Record<string, unknown>> }>('../i18n/locales/*.json', {
  eager: true,
})

/**
 * The owner, 12 Nov 2026: a subscriber who pays by transfer must know on which account, by
 * when and with which reference to pay. The bank details were there; the reference (the
 * ABO- number of the invoice Alice names to pay, `invoice_due`) and its last day were not.
 * Told, never inferred: none when Alice names no invoice.
 */
describe('the transfer block says the reference and the day', () => {
  const block = PAGE.slice(PAGE.indexOf("t('billing.byTransfer')"))

  it('reads the invoice Alice names, only where the transfer is offered', () => {
    expect(PAGE).toContain('const transferDue = transferShown ? invoiceDueOf(current?.invoice_due) : null')
    expect(block).toContain('{transferDue.number}')
    expect(block).toContain('{day(transferDue.due_on)}')
    // Inside the bank details, before the button « J'ai fait le virement ».
    expect(block.indexOf('{transferDue.number}')).toBeLessThan(block.indexOf("t('billing.declareTransfer')"))
  })

  it('says the day in the banner’s words', () => {
    expect(BANNER).toContain('date: day(invoice.due_on)')
  })

  it('in every language of the product', () => {
    const files = Object.entries(LOCALES)
    expect(files.length).toBeGreaterThanOrEqual(2)
    for (const [path, mod] of files) {
      const section = mod.default.billing as Record<string, string>
      expect(section.transferReference, path).toBeTruthy()
      expect(section.transferDueOn, path).toBeTruthy()
    }
  })
})

/**
 * The owner, 12 Nov 2026 (« uniformise les deux-points »): the labels of the transfer block
 * carry their colon, as in Immo and RH: « Titulaire : » in French (a non-breaking space
 * before it), « Account holder: » elsewhere. IBAN and BIC were written in the page with no
 * colon: they are keys too, so that each language writes its own.
 */
describe('the transfer block labels carry their colon', () => {
  const start = PAGE.indexOf("t('billing.byTransfer')")
  const block = PAGE.slice(start, PAGE.indexOf("t('billing.declareTransfer')", start))
  const KEYS = ['holder', 'iban', 'bic', 'transferReference', 'transferDueOn']

  it('every label of the block is a key, IBAN and BIC included', () => {
    for (const key of KEYS) expect(block).toContain(`{t('billing.${key}')}</dt>`)
    expect(block).not.toMatch(/<dt[^>]*>(?!\{t\()/)
  })

  it('each language writes the colon its own way', () => {
    for (const [file, mod] of Object.entries(LOCALES)) {
      const billing = mod.default.billing as Record<string, unknown>
      for (const key of KEYS) {
        const said = String(billing[key])
        if (file.endsWith('/fr.json')) expect(said, `billing.${key} in ${file}`).toMatch(/\S\u00A0:$/)
        else expect(said, `billing.${key} in ${file}`).toMatch(/\S:$/)
      }
    }
  })
})

import { describe, expect, it } from 'vitest'
import type { TermsDocumentStatus, TermsStatus } from '@/api/terms'
import { seenKeyOf, upcomingTerms } from '@/lib/terms'
import { subscriptionBannerOf } from '@/lib/subscriptionBanner'
import type { BillingSubscription } from '@/types'
import BANNER from './UpcomingTermsBanner.tsx?raw'
import GATE from './TermsGate.tsx?raw'
import READER from './TermsReader.tsx?raw'
import SHELL from '../layout/Shell.tsx?raw'
import SUBSCRIPTION_BANNER from '../layout/SubscriptionBanner.tsx?raw'

/**
 * Make the code say what the texts say (the owner, 12 Nov 2026): a new version of the
 * terms is announced during its notice (CGU 10.1), and an ended subscription keeps thirty
 * days to read and export (CGV 7.4).
 */
const state = (over: Partial<TermsDocumentStatus> = {}): TermsDocumentStatus => ({
  version: '2026-10', product: 'invest', audience: 'manager', effective_from: '2026-10-01',
  accepted_version: '2026-10', accepted_at: null, up_to_date: true, anything_to_accept: true,
  pending: false, ...over,
})
const ahead = {
  version: '2026-12', product: 'invest', audience: 'manager', effective_from: '2026-12-15',
  summary_of_changes: 'Article 9.',
}
const status = (over: Partial<TermsStatus> = {}): TermsStatus => ({
  cgu: state(), cgv: null, dpa: null, unavailable: false, subscriber: true, ...over,
})

describe('a new version of the terms is announced during its notice (CGU 10.1)', () => {
  it('shows the version Alice announces', () => {
    expect(upcomingTerms(status({ cgu: state({ upcoming: ahead }) }))).toEqual([{ kind: 'cgu', upcoming: ahead }])
  })

  it('shows nothing when nothing is announced, or Alice is unreachable', () => {
    expect(upcomingTerms(status())).toEqual([])
    expect(upcomingTerms(status({ cgu: state({ upcoming: ahead }), unavailable: true }))).toEqual([])
    expect(upcomingTerms(null)).toEqual([])
  })

  it('keeps the order the documents are asked in', () => {
    const s = status({ cgu: state({ upcoming: ahead }), dpa: state({ upcoming: ahead }), cgv: state({ upcoming: ahead }) })
    expect(upcomingTerms(s).map((x) => x.kind)).toEqual(['cgu', 'cgv', 'dpa'])
  })

  it('leaves out a version this reader set aside, and only that version', () => {
    const seen = new Set([seenKeyOf('cgu', '2026-12')])
    expect(upcomingTerms(status({ cgu: state({ upcoming: ahead }) }), (k) => seen.has(k))).toEqual([])
    const next = { ...ahead, version: '2027-01' }
    expect(upcomingTerms(status({ cgu: state({ upcoming: next }) }), (k) => seen.has(k))).toHaveLength(1)
  })

  it('is drawn on every page of the shell, from the status the gate read', () => {
    expect(SHELL).toContain('<UpcomingTermsBanner />')
    expect(GATE).toContain('<TermsStatusContext.Provider value={status}>')
    expect(BANNER).toContain('useContext(TermsStatusContext)')
  })

  it('reads the text announced, in its version, and says it is ahead', () => {
    expect(BANNER).toContain('version: open.upcoming.version')
    expect(BANNER).toContain('<TermsReader')
    expect(READER).toContain('ahead={ahead}')
    expect(READER).toContain("'terms.versionLineAhead'")
  })
})

describe('an ended subscription reads and exports for thirty days (CGV 7.4)', () => {
  it('still tells the subscriber it ended, and says until when on the banner', () => {
    const ended = {
      managed: true, is_holder: true, unavailable: false, is_blocked: true, suspended: false, ended: true,
      exports_open: true, export_until: '2026-12-01T00:00:00+00:00',
    } as BillingSubscription
    expect(subscriptionBannerOf(ended, false, '2026-11-13')).toBe('ended')
    expect(SUBSCRIPTION_BANNER).toContain("t('subscriptionBanner.endedExports'")
  })
})

import { apiClient } from './client'

/**
 * The terms of use (`cgu`), the terms of sale (`cgv`) and the data processing agreement
 * (`dpa`, art. 28 GDPR, the owner 13 Oct 2026), as Alice holds them.
 *
 * 🔴 THROUGH THIS PRODUCT'S SERVER, NEVER TO ALICE DIRECTLY: recording an acceptance needs
 * the internal key, and a key in a bundle is a key everyone has. This product keeps no
 * copy of a text: every one of these calls is relayed.
 *
 * ⚠️ EVERY CALL SKIPS THE GLOBAL TOAST: each screen says the refusal in place (a stale
 * version, a console that does not answer), where the person can act on it.
 */
export type TermsKind = 'cgu' | 'cgv' | 'dpa'
/** What the public route reads: the three above, and `prv`, the privacy notice and legal
 *  information, read by anybody and accepted by nobody (the owner, 1 Nov 2026). */
export type PublicTermsKind = TermsKind | 'prv'

/** The documents only the subscriber accepts, in the order the gate asks them. */
export const SUBSCRIBER_KINDS = ['cgv', 'dpa'] as const
export type SubscriberKind = (typeof SUBSCRIBER_KINDS)[number]

/** One text, in the reader's language or, failing that, in French (`fell_back`). */
export interface TermsText {
  kind: PublicTermsKind
  product: string
  audience: string
  version: string
  language: string
  requested_language: string
  fell_back: boolean
  title: string
  /** Markdown, the binding text; shown as written only when Alice sends no `body_html`. */
  body: string
  /**
   * The same text laid out by Alice, built from the ESCAPED Markdown source and holding
   * only layout tags. Absent while Alice does not serve it yet.
   */
  body_html?: string
  /** A calendar day, `yyyy-MM-dd`. */
  effective_from: string
  summary_of_changes: string | null
}

/** Where this account stands with one document. */
/**
 * A version Alice published and that is not yet in force, announced during its notice
 * (terms of use, article 10.1: published and announced at least thirty days before it
 * takes effect, with a summary of what changes; the owner, 12 Nov 2026).
 */
export interface TermsUpcoming {
  version: string
  product: string | null
  audience: string | null
  /** A calendar day, `yyyy-MM-dd`. */
  effective_from: string
  summary_of_changes: string | null
}

export interface TermsDocumentStatus {
  /** The version asked; null when nothing is published. */
  version: string | null
  product: string | null
  audience: string | null
  effective_from: string | null
  accepted_version: string | null
  /** An instant. */
  accepted_at: string | null
  up_to_date: boolean
  anything_to_accept: boolean
  /** Owed now: the gate shows it. */
  pending: boolean
  /** The next version, announced during its notice; absent from an older server. */
  upcoming?: TermsUpcoming | null
}

export interface TermsStatus {
  cgu: TermsDocumentStatus | null
  /** The subscriber's only. */
  cgv: TermsDocumentStatus | null
  /**
   * The data processing agreement, the subscriber's only like the terms of sale. Absent or
   * null while the console does not serve it: nothing is asked.
   */
  dpa?: TermsDocumentStatus | null
  /** The console did not answer: nothing is asked, the application opens. */
  unavailable: boolean
  /** This account holds the licence. */
  subscriber: boolean
}

/** One acceptance, as Alice recorded it. */
export interface TermsAcceptance {
  kind: TermsKind
  product: string
  audience: string
  version: string
  language: string
  title: string | null
  effective_from: string | null
  method: string | null
  /** An instant. */
  accepted_at: string
}

export interface TermsHistory {
  entries: TermsAcceptance[]
  unavailable: boolean
}

/** Which text to read: the scope a status or a history entry names. */
export interface TermsTextQuery {
  kind: TermsKind
  language: string
  version?: string | null
  product?: string | null
  audience?: string | null
}

/** One sub-processor, as Alice lists it (her words, in French). */
export interface Subprocessor {
  name: string
  service: string
  data: string
  location: string
  safeguards: string | null
  products_label: string
  website: string | null
  /** A calendar day, `yyyy-MM-dd`: from when it receives data. */
  effective_from: string
  /** A calendar day: when it stops, when its withdrawal is announced. */
  ended_on: string | null
}

/** The sub-processors the agreement authorises: today's, and the additions announced. */
export interface Subprocessors {
  current: Subprocessor[]
  announced: Subprocessor[]
  contact_email: string | null
}

const quiet = { skipErrorToast: true }

export const termsApi = {
  status: () => apiClient.get<TermsStatus>('/terms/status', quiet),
  text: ({ kind, language, version, product, audience }: TermsTextQuery) =>
    apiClient.get<TermsText>('/terms/text', {
      ...quiet,
      params: {
        kind,
        language,
        ...(version ? { version } : {}),
        ...(product ? { product } : {}),
        ...(audience ? { audience } : {}),
      },
    }),
  accept: (body: { kind: TermsKind; version: string; language: string }) =>
    apiClient.post('/terms/accept', body, quiet),
  history: () => apiClient.get<TermsHistory>('/terms/history', quiet),
  /** What a person signing up is asked, or the privacy notice (`prv`) anybody reads: no
   *  session. 404: no box, or no notice published yet; 503: Alice is silent. */
  forSignup: (kind: PublicTermsKind, language: string) =>
    apiClient.get<TermsText>('/public/terms', { ...quiet, params: { kind, language } }),
  /** The sub-processors, public like the text: shown under the agreement. 503: say so. */
  subprocessors: () => apiClient.get<Subprocessors>('/public/terms/subprocessors', quiet),
}

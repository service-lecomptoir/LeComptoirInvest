import { apiClient } from './client'

/**
 * The terms of use (`cgu`) and the terms of sale (`cgv`), as Alice holds them.
 *
 * 🔴 THROUGH THIS PRODUCT'S SERVER, NEVER TO ALICE DIRECTLY: recording an acceptance needs
 * the internal key, and a key in a bundle is a key everyone has. This product keeps no
 * copy of a text: every one of these calls is relayed.
 *
 * ⚠️ EVERY CALL SKIPS THE GLOBAL TOAST: each screen says the refusal in place (a stale
 * version, a console that does not answer), where the person can act on it.
 */
export type TermsKind = 'cgu' | 'cgv'

/** One text, in the reader's language or, failing that, in French (`fell_back`). */
export interface TermsText {
  kind: TermsKind
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
}

export interface TermsStatus {
  cgu: TermsDocumentStatus | null
  /** The subscriber's only. */
  cgv: TermsDocumentStatus | null
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
  /** What a person signing up is asked: no session. 404: no box; 503: no sign-up. */
  forSignup: (kind: TermsKind, language: string) =>
    apiClient.get<TermsText>('/public/terms', { ...quiet, params: { kind, language } }),
}

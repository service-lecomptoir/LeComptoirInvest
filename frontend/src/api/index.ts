import { apiClient } from './client'
import type {
  CapitalCall, Distribution, Investor, Me, Movement, Portfolio, Project,
  Statement, SubscriptionRequest, Waterfall,
  BillingSubscription, PaymentMethods, BillingPlan, BillingInvoice, BillingStatus,
  PerformanceBlock, CapitalAccountLine, ProjectValuation, LateCall, InvestorCategory,
  CamtImport, Fund, FundNetAssetValue, CallNotice, InvestorQuota,
} from '@/types'

export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<{ access_token: string; role: string; must_change_password: boolean }>(
      '/auth/login', { email, password }, { skipErrorToast: true }),
  // A reload keeps only the token: the application asks again WHO it serves rather
  // than trusting a role copied into local storage, which a user can edit and which
  // stays frozen after a change decided elsewhere.
  me: () => apiClient.get<Me>('/auth/me'),
  changePassword: (currentPassword: string, newPassword: string) =>
    apiClient.post('/auth/change-password',
      { current_password: currentPassword, new_password: newPassword },
      { skipErrorToast: true }),
}

export const investorsApi = {
  list: () => apiClient.get<Investor[]>('/investors'),
  me: () => apiClient.get<Investor>('/investors/me'),
  // 🔴 BOTH DOORS THE ALLOWANCE IS COUNTED THROUGH CARRY `accept_overage`, and the
  // second one does not look like a door. Registering an investor obviously adds one;
  // REVERSING A REFUSAL does too, because a refused file is not billed and an un-refused
  // one is. A fund at its ceiling could otherwise refuse a hundred people and un-refuse
  // them one at a time, for free. Both go through `withOverageConsent`.
  create: (body: Record<string, unknown>, acceptOverage = false) =>
    apiClient.post<Investor>('/investors', body, { params: { accept_overage: acceptOverage } }),
  setKyc: (id: string, body: Record<string, unknown>, acceptOverage = false) =>
    apiClient.post<Investor>(`/investors/${id}/kyc`, body, {
      params: { accept_overage: acceptOverage },
    }),
  // Where the register stands against the plan. Read-only: it announces, it never refuses,
  // and it shares its arithmetic with the guard that does.
  quota: () => apiClient.get<InvestorQuota>('/investors/quota'),
  // Which protections apply, and on what declared basis. Its own endpoint on purpose:
  // folding it into the KYC verdict would let an « accepted » click quietly lift a cap.
  setEligibility: (id: string, body: { category: InvestorCategory; loss_bearing_capacity?: string | null }) =>
    apiClient.post<Investor>(`/investors/${id}/eligibility`, body),
  bankDetails: (id: string) =>
    apiClient.get<{ iban: string | null; bic: string | null; virtual_iban: string | null }>(
      `/investors/${id}/bank-details`),
}

export const subscriptionsApi = {
  requests: () => apiClient.get<SubscriptionRequest[]>('/subscription-requests'),
  request: (body: Record<string, unknown>) =>
    apiClient.post<SubscriptionRequest>('/subscription-requests', body),
  decide: (id: string, body: Record<string, unknown>) =>
    apiClient.post<SubscriptionRequest>(`/subscription-requests/${id}/decide`, body),
  convert: (id: string, body: Record<string, unknown>) =>
    apiClient.post(`/subscriptions/${id}/convert`, body),
  portfolio: (investorId?: string) =>
    apiClient.get<Portfolio>('/portfolio', { params: investorId ? { investor_id: investorId } : {} }),
}

export const treasuryApi = {
  balance: () => apiClient.get<Record<string, string>>('/treasury/balance'),
  unattributed: () => apiClient.get<Movement[]>('/treasury/unattributed'),
  importMovements: (lines: Record<string, unknown>[]) =>
    apiClient.post<Movement[]>('/treasury/movements', lines),
  // The bank's own statement. Retyped money carries a typo, and the typo lands on the
  // reference — the single field the whole matching rests on.
  importCamt: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return apiClient.post<CamtImport>('/treasury/movements/camt', body)
  },
  attribute: (movementId: string, body: Record<string, unknown>) =>
    apiClient.post(`/treasury/movements/${movementId}/attribute`, body),
  calls: () => apiClient.get<CapitalCall[]>('/treasury/calls'),
  openCall: (body: Record<string, unknown>) => apiClient.post<CapitalCall>('/treasury/calls', body),
  // `as_of` is always sent: whether a call is late depends on a date, and a server reading
  // its own clock would answer differently for two readers on the day it falls due.
  lateCalls: (asOf: string) =>
    apiClient.get<LateCall[]>('/treasury/late-calls', { params: { as_of: asOf } }),
}

export const projectsApi = {
  list: () => apiClient.get<Project[]>('/projects'),
  create: (body: Record<string, unknown>) => apiClient.post<Project>('/projects', body),
  deploy: (id: string, body: Record<string, unknown>) =>
    apiClient.post(`/projects/${id}/deployments`, body),
  recordReturn: (id: string, body: Record<string, unknown>) =>
    apiClient.post(`/projects/${id}/returns`, body),
  setStatus: (id: string, body: Record<string, unknown>) =>
    apiClient.post<Project>(`/projects/${id}/status`, body),
  // A valuation is an opinion with an author and a date. The author is the signed-in
  // manager and is never sent from here: a signature the caller chooses is worth nothing.
  valuations: (id: string) =>
    apiClient.get<ProjectValuation[]>(`/projects/${id}/valuations`),
  recordValuation: (id: string, body: { valued_on: string; amount: string; basis?: string }) =>
    apiClient.post<ProjectValuation>(`/projects/${id}/valuations`, body),
}

export const distributionsApi = {
  // A blocked proposal is a NORMAL answer here, not a failure: it names the debt that has
  // to be served first. Hence `skipErrorToast` — the screen shows the reason in place.
  propose: (body: Record<string, unknown>) =>
    apiClient.post<Waterfall>('/distributions/propose', body, { skipErrorToast: true }),
  decide: (body: Record<string, unknown>) => apiClient.post('/distributions', body),
  list: () => apiClient.get<Distribution[]>('/distributions'),
  pay: (id: string, body: Record<string, unknown>) => apiClient.post(`/distributions/${id}/pay`, body),
  debt: (currency: string, asOf: string) =>
    apiClient.get<{ currency: string; owed_to_lenders: string; unmeasurable: string[] }>(
      '/distributions/debt', { params: { currency, as_of: asOf } }),
}

export const statementsApi = {
  get: (year: number, investorId?: string) =>
    apiClient.get<Statement>(`/statements/${year}`, {
      params: investorId ? { investor_id: investorId } : {},
    }),
  /**
   * The same statement, as a document.
   *
   * ⚠️ `responseType: 'blob'`, AND IT IS MANDATORY. Without it axios decodes the bytes of
   * the PDF as UTF-8 text: the response arrives, nothing fails, and the saved file is a
   * corrupt PDF that the reader discovers on opening it, later, elsewhere.
   *
   * 🔴 THE LANGUAGE OF THE DOCUMENT IS THE INVESTOR'S, not that of this screen. The server
   * decides it alone; the `Accept-Language` header the interceptor sets does not touch it.
   * A French manager who downloads the statement of a British investor gets an English
   * document, and that is the point.
   */
  pdf: (year: number, investorId?: string) =>
    apiClient.get<Blob>(`/statements/${year}/pdf`, {
      params: investorId ? { investor_id: investorId } : {},
      responseType: 'blob',
    }),
}

/**
 * The manager's subscription TO THE PRODUCT.
 *
 * ⚠️ `billingApi` and `subscriptionsApi` do not speak of the same thing, and that is why
 * they carry unrelated names: the second one is the investors subscribing to the fund. A
 * shared name would have ended up mixing the two on one screen.
 */
export const billingApi = {
  mine: () => apiClient.get<BillingSubscription>('/billing'),
  paymentMethods: () => apiClient.get<PaymentMethods>('/billing/payment-methods'),
  status: () => apiClient.get<BillingStatus>('/billing/status'),
  plans: () => apiClient.get<BillingPlan[]>('/billing/plans'),
  // The refusal is SHOWN IN PLACE, next to the button: an unreachable console is
  // useful information, not a fleeting red banner at the top of the screen.
  checkout: (planId?: string) =>
    apiClient.post<{ url?: string }>('/billing/checkout', planId ? { plan_id: planId } : {},
      { skipErrorToast: true }),
  portal: () => apiClient.post<{ url?: string }>('/billing/portal', {}, { skipErrorToast: true }),
  declareTransfer: () => apiClient.post('/billing/declare-transfer', {}, { skipErrorToast: true }),
  cancelTransfer: () => apiClient.post('/billing/cancel-transfer', {}, { skipErrorToast: true }),
  changePlan: (planId: string) =>
    apiClient.post('/billing/change-plan', { plan_id: planId }, { skipErrorToast: true }),
  previewChange: (planId: string) =>
    apiClient.post<{ amount_due?: number; currency?: string }>(
      '/billing/change-plan-preview', { plan_id: planId }, { skipErrorToast: true }),
  invoices: () => apiClient.get<BillingInvoice[]>('/billing/invoices'),
  invoicePdfUrl: (id: string) => `/billing/invoices/${id}/pdf`,
}

export const performanceApi = {
  // `as_of` is always sent: a server that dated the report itself would give two readers
  // in different places a different « today », on the same fund.
  get: (asOf: string, investorId?: string) =>
    apiClient.get<PerformanceBlock[]>('/performance', {
      params: { as_of: asOf, ...(investorId ? { investor_id: investorId } : {}) },
    }),
  capitalAccount: (since: string, until: string, investorId?: string) =>
    apiClient.get<CapitalAccountLine[]>('/capital-account', {
      params: { since, until, ...(investorId ? { investor_id: investorId } : {}) },
    }),
}

export const noticeApi = {
  // ⚠️ READING IS A GET AND SENDING IS A POST, and they are not the same call with a flag.
  // A screen that marked the call as notified when it merely rendered the text would
  // silence the chasing list for anybody who looked at it.
  preview: (callId: string, asOf: string) =>
    apiClient.get<CallNotice>(`/treasury/calls/${callId}/notice`, {
      params: { as_of: asOf },
      skipErrorToast: true,
    }),
  send: (callId: string, asOf: string) =>
    apiClient.post<CallNotice>(`/treasury/calls/${callId}/notice`, null, {
      params: { as_of: asOf },
    }),
}

export const fundsApi = {
  list: () => apiClient.get<Fund[]>('/funds'),
  create: (body: Record<string, unknown>) => apiClient.post<Fund>('/funds', body),
  setStatus: (id: string, body: { status: string; closed_on?: string | null }) =>
    apiClient.post<Fund>(`/funds/${id}/status`, body),
  // ⚠️ `fund_id` OMITTED MEANS « the vehicle no fund row was created for », not « all of
  // them added together ». The server reads it that way in the waterfall and in the
  // performance too; sending a different meaning from here would produce a total that
  // reconciles with nothing.
  netAssetValue: (params: { as_of: string; currency: string; fund_id?: string }) =>
    apiClient.get<FundNetAssetValue[]>('/funds/net-asset-value', { params }),
}

/** A catalogue plan, as the console sells it (`GET /public/plans`). */
export interface PublicPlan {
  id: string
  name: string
  description: string | null
  /** The most investors covered: the billed unit of this product. `null`: no ceiling. */
  investor_limit: number | null
  monthly_price: number
  overage_price: number
  tva_rate: number
  /** A quotation: never shown on the public page, which lists the catalogue only. */
  sur_devis: boolean
}

/** A country the platform serves, as the console lists it. */
export interface Country {
  code: string
  name: string
  /** « SIREN / SIRET » in France, the local name of the company number elsewhere. */
  number_label: string
}

/** One suggestion of the address search, as the console words it. */
export interface AddressRow {
  street: string
  zip_code: string
  city: string
  label: string
  department?: string
  region?: string
  country?: string
}

/** What the register says of a company number (`unreachable` when nobody looked). */
export interface CompanyRow {
  status: string
  name?: string | null
  street?: string | null
  zip_code?: string | null
  city?: string | null
  siret?: string | null
  ape?: string | null
  legal_form?: string | null
}

/** The console's answer to a sign-up. */
export interface SignupOutcome {
  /** `confirmation_sent`, `account_exists`, `account_created`, `received`. */
  status: string
  message: string
  login_url: string | null
  subscription_url: string | null
}

/**
 * What is open before any account exists: the plans, the sign-up and the common lookups.
 *
 * 🔴 THROUGH THIS PRODUCT'S OWN SERVER, which relays to the console (28 Sept 2026: « tout
 * ce qui est commun, ça sera dans Alice »). The gateway's policy is `connect-src 'self'`: a
 * browser call to a register would be blocked, silently.
 *
 * ⚠️ THE SIGN-UP SKIPS THE GLOBAL TOAST: the form shows the refusal in place, next to the
 * field to correct, and a toast on top would say it twice.
 */
export const publicApi = {
  plans: () => apiClient.get<PublicPlan[]>('/public/plans'),
  countries: () => apiClient.get<Country[]>('/public/lookups/countries'),
  company: (number: string, signal?: AbortSignal) =>
    apiClient.get<CompanyRow>('/public/lookups/company', { params: { number }, signal }),
  address: (q: string, country: string, signal?: AbortSignal) =>
    apiClient.get<AddressRow[]>('/public/lookups/address', { params: { q, country }, signal }),
  accessRequest: (body: Record<string, unknown>) =>
    apiClient.post<SignupOutcome>('/public/access-request', body, { skipErrorToast: true }),
}

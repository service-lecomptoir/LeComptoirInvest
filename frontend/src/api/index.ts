import { apiClient } from './client'
import type {
  CapitalCall, Distribution, Investor, Me, Movement, Portfolio, Project,
  Statement, SubscriptionRequest, Waterfall,
  BillingSubscription, PaymentMethods, BillingPlan, BillingInvoice, BillingStatus,
  PerformanceBlock, CapitalAccountLine, ProjectValuation,
} from '@/types'

export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<{ access_token: string; role: string; must_change_password: boolean }>(
      '/auth/login', { email, password }, { skipErrorToast: true }),
  // Un rechargement ne garde que le jeton : l'application redemande QUI elle sert plutôt
  // que de faire confiance à un rôle recopié dans le stockage local, qu'un utilisateur
  // peut éditer et qui reste figé après un changement décidé ailleurs.
  me: () => apiClient.get<Me>('/auth/me'),
  changePassword: (currentPassword: string, newPassword: string) =>
    apiClient.post('/auth/change-password',
      { current_password: currentPassword, new_password: newPassword },
      { skipErrorToast: true }),
}

export const investorsApi = {
  list: () => apiClient.get<Investor[]>('/investors'),
  me: () => apiClient.get<Investor>('/investors/me'),
  create: (body: Record<string, unknown>) => apiClient.post<Investor>('/investors', body),
  setKyc: (id: string, body: Record<string, unknown>) =>
    apiClient.post<Investor>(`/investors/${id}/kyc`, body),
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
  attribute: (movementId: string, body: Record<string, unknown>) =>
    apiClient.post(`/treasury/movements/${movementId}/attribute`, body),
  calls: () => apiClient.get<CapitalCall[]>('/treasury/calls'),
  openCall: (body: Record<string, unknown>) => apiClient.post<CapitalCall>('/treasury/calls', body),
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
}

/**
 * L'abonnement du gestionnaire AU PRODUIT.
 *
 * ⚠️ `billingApi` et `subscriptionsApi` ne parlent pas de la même chose, et c'est pour
 * cela qu'ils portent des noms sans rapport : le second, ce sont les investisseurs qui
 * souscrivent au fonds. Un nom partagé aurait fini par mêler les deux dans un écran.
 */
export const billingApi = {
  mine: () => apiClient.get<BillingSubscription>('/billing'),
  paymentMethods: () => apiClient.get<PaymentMethods>('/billing/payment-methods'),
  status: () => apiClient.get<BillingStatus>('/billing/status'),
  plans: () => apiClient.get<BillingPlan[]>('/billing/plans'),
  // Le refus est MONTRÉ EN PLACE, à côté du bouton : une console injoignable est une
  // information utile, pas une bannière rouge fugace en haut de l'écran.
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

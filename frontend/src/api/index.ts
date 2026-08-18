import { apiClient } from './client'
import type {
  CapitalCall, Distribution, Investor, Movement, Portfolio, Project,
  Statement, SubscriptionRequest, Waterfall,
} from '@/types'

export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<{ access_token: string; role: string; must_change_password: boolean }>(
      '/auth/login', { email, password }, { skipErrorToast: true }),
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

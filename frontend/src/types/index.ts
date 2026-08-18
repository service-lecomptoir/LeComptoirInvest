/** The shapes the API returns. Kept close to the backend's names on purpose: two
 *  vocabularies for one fact is how a screen ends up showing a different figure. */

export type Instrument = 'equity' | 'loan'
export type KycStatus = 'pending' | 'accepted' | 'refused' | 'review'

export interface User {
  id: string
  email: string
  full_name: string | null
  sees_whole_fund: boolean
}

export interface Me {
  id: string
  email: string
  account_name: string | null
  role: string
  sees_whole_fund: boolean
  must_change_password: boolean
}

export interface Investor {
  id: string
  kind: string
  display_name: string
  email: string | null
  country: string | null
  kyc_status: KycStatus
  kyc_reviewed_on: string | null
  accepts_money: boolean
}

export interface SubscriptionRequest {
  id: string
  instrument: Instrument
  amount: string
  currency: string
  requested_on: string
  status: string
  decision_reason: string | null
  /** L'engagement né de cette demande. NULL tant qu'elle est en attente, et NULL pour
   *  toujours si elle est refusée — c'est ce qui rend les deux lignes utiles séparément. */
  subscription_id: string | null
}

export interface Position {
  subscription_id: string
  instrument: Instrument
  currency: string
  committed: string
  called: string
  contributed: string
  outstanding_commitment: string
  capital_at_work: string
  income_received: string
  net_received: string
}

export interface Portfolio {
  positions: Position[]
  totals_by_currency: Record<string, Record<string, string>>
}

export interface Movement {
  id: string
  amount: string
  currency: string
  value_date: string
  label: string | null
  counterparty_name: string | null
  proposal: {
    investor_id: string | null
    capital_call_id: string | null
    basis: string
    third_party_payer: boolean
    explanation: string
  } | null
}

export interface CapitalCall {
  id: string
  subscription_id: string
  reference: string
  amount: string
  currency: string
  called_on: string
  due_on: string
  notified_on: string | null
  epc_qr: string | null
}

export interface Project {
  id: string
  name: string
  status: string
  currency: string
  target_amount: string | null
  deployed: string
  capital_returned: string
  income_returned: string
  outstanding: string
  gain: string
  multiple: string | null
}

export interface WaterfallShare {
  subscription_id: string
  investor_id: string
  investor_name: string
  instrument: Instrument
  capital_amount: string
  income_amount: string
}

export interface Waterfall {
  currency: string
  available: string
  as_of: string
  shares: WaterfallShare[]
  distributed: string
  undistributed: string
  debt_remaining: string
  blocked_reason: string | null
  unknown: string[]
}

export interface Distribution {
  id: string
  subscription_id: string
  capital_amount: string
  income_amount: string
  withholding_amount: string
  currency: string
  decided_on: string
  paid_on: string | null
}

export interface StatementLine {
  instrument: Instrument
  currency: string
  income_gross: string
  withholding: string
  income_net: string
  capital_repaid: string
  received: string
}

export interface Statement {
  investor_id: string
  investor_name: string
  year: number
  lines: StatementLine[]
  totals_by_currency: Record<string, Record<string, string>>
  capital_at_work: Record<string, string>
  decided_not_paid: Record<string, string>
}

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
  /** ⚠️ THE TRUTH THE GATES APPLY, staleness included. It used to read the status alone, so
   *  a file three years past its review still showed « accepts money » while every endpoint
   *  that moves money refused it. */
  accepts_money: boolean
  /** Why money is refused, when it is: « never accepted » and « out of date » call for
   *  different actions from whoever reads it. */
  refusal_reason: string | null
  category: InvestorCategory | null
  loss_bearing_capacity: string | null
  /** The amount above which a risk warning must be acknowledged. null is never « no limit ». */
  warning_threshold: string | null
  threshold_reason: string | null
}

export type InvestorCategory = 'retail' | 'sophisticated' | 'professional'

export interface LateCall {
  call_id: string
  reference: string
  investor_id: string
  investor_name: string
  currency: string
  called: string
  received: string
  outstanding: string
  due_on: string
  days_late: number
  late_interest: string
  /** True when the notice was never sent: the fund is late, not the investor. */
  never_notified: boolean
  last_reminded_on: string | null
  reminder_due: boolean
  reminder_blocked_reason: string | null
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
  /** The manager's performance share, on what exceeds the hurdle. */
  carried_interest: string
  /** ⚠️ SEPARATE FROM THE CARRY, and it must stay separate on screen. A fee is owed whether
   *  the fund performs or not; one combined figure would hide a flat year in which the
   *  manager was still paid. */
  management_fee: string
  /** What is still missing before the hurdle is met. Zero means the carry has begun. */
  preferred_remaining: string
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

// ── L'abonnement AU LOGICIEL ────────────────────────────────────────────────────────
// ⚠️ À NE PAS CONFONDRE avec `SubscriptionRequest`, qui est l'engagement d'un investisseur
// dans un fonds. Le métier a pris le mot « souscription » ; ce que le gestionnaire paie
// pour utiliser le produit s'appelle donc « billing » d'un bout à l'autre du code.

export interface BillingSubscription {
  /** false = aucune console ne pilote cette instance. Ce n'est PAS « gratuit ». */
  managed: boolean
  plan_name: string | null
  monthly_price: number | null
  is_blocked: boolean
  features: string[] | null
  access_until: string | null
  fund_limit: number | null
}

export interface PaymentMethods {
  card_enabled: boolean
  transfer_enabled: boolean
  currency: string
  transfer: {
    holder: string | null
    iban: string | null
    bic: string | null
    bank: string | null
    instructions: string | null
  } | null
}

export interface BillingPlan {
  id: string
  name: string
  monthly_price: number
  /** 🔴 THE PLATFORM'S GENERIC NAME, relayed straight from Alice. It counts properties at
   *  Immo, homes at Sejour, shops at Market, investors here — one key for five products,
   *  and each product's WORD lives in Alice's registry. Reading it under any other name
   *  leaves it undefined, and an undefined ceiling reads as « unlimited ». */
  managed_limit: number | null
}

export interface BillingInvoice {
  id: string
  number?: string | null
  period?: string | null
  issued_at?: string | null
  amount?: number | null
  status?: string | null
  paid_at?: string | null
}

export interface BillingStatus {
  stripe_enabled: boolean
  has_subscription: boolean
  status?: string | null
  current_period_end?: string | null
  cancel_at_period_end?: boolean
  payment_method?: string | null
  transfer_pending?: boolean
}

// ── Performance ─────────────────────────────────────────────────────────────────────
// ⚠️ EVERY RATIO IS NULLABLE ON PURPOSE. Three of the four need a valuation of what is
// still held, and this product values nothing. A number where the answer is « unknown »
// would under-state every open fund, and nobody disputes a return that looks too low.

export interface PerformanceBlock {
  currency: string
  as_of: string
  paid_in: string
  distributed: string
  residual_value: string | null
  dpi: string | null
  rvpi: string | null
  tvpi: string | null
  irr: string | null
  /** True when the rate covers only what has already come back. */
  irr_is_realised_only: boolean
  unavailable_reason: string | null
}

export interface CapitalAccountLine {
  currency: string
  since: string
  until: string
  opening_balance: string
  contributions: string
  capital_returned: string
  income: string
  withheld: string
  outstanding_commitment: string
  closing_balance: string
  net_paid: string
}

export interface ProjectValuation {
  id: string
  project_id: string
  /** The day the value is judged AS OF, never the day it was typed. */
  valued_on: string
  amount: string
  currency: string
  /** Who formed the judgement. A valuation nobody signed is one nobody can be asked about. */
  valued_by: string
  basis: string | null
}

export interface CamtImport {
  imported: Movement[]
  /** 🔴 ONE LINE PER REFUSAL, never a count. « 3 lines ignored » is unactionable, and a
   *  statement quietly short of one entry reconciles to a figure that is wrong and looks
   *  right. */
  refused: string[]
  /** Already known by (account, external id): a re-import must change nothing. */
  already_known: number
}

export interface CallNotice {
  /** Which letter this is. The demand and the reminder are two different statements to
   *  somebody about their money, never one text with a flag. */
  kind: 'first_notice' | 'reminder'
  /** 🔴 THE INVESTOR'S LANGUAGE, NOT THE READER'S. Shown so a French manager previewing an
   *  English letter reads it as deliberate rather than as a bug. */
  language: string
  to: string | null
  subject: string
  body: string
  qr_payload: string | null
  qr_unavailable_reason: string | null
  /** False when this installation has no SMTP configured: the screen says so before the
   *  click rather than after it. */
  sending_is_configured: boolean
  sent_on: string | null
}

export type FundStatus = 'raising' | 'investing' | 'harvesting' | 'closed'

export interface FundTerms {
  /** The hurdle, as a rate: 0.08 is eight per cent a year. */
  preferred_return: number
  carried_interest: number
  management_fee: number
}

export interface Fund {
  id: string
  name: string
  status: FundStatus
  currency: string
  iban: string | null
  terms: FundTerms | null
  opened_on: string | null
  closed_on: string | null
  mandate: string | null
  /** 🔴 FALSE MEANS NO NET ASSET VALUE CAN BE COMPUTED. A vehicle with no account of its
   *  own, while another exists, shares cash that no rule can split: a bank line says
   *  nothing about which fund the euro was for. The row says so before the figure page
   *  has to. */
  cash_is_separable: boolean
}

export interface FundNetAssetValue {
  currency: string
  as_of: string
  projects: string
  cash: string
  debt_to_lenders: string
  /** Named, never counted: « 2 projets » sends the reader hunting, the names send them
   *  to the two records that would produce the total. */
  unvalued: string[]
  total: string | null
  unavailable_reason: string | null
}

# The firm's licence and what it bills

Alice bills Invest's subscriptions from 1 January 2027, on the number of investors. This
document says, in one place, who is held to the licence, what is counted, and through which
doors an investor enters the plan. Decisions of the owner, 8 November 2026 (the same as Le
Comptoir Immo's, `docs/THE_LICENCE_AND_WHAT_IT_BILLS.md` there).

## The licence is the firm's

Alice opens ONE licence, for the account that IS the management company: a `manager` with
no `firm_id` (`User.holds_the_licence`). Every account of the firm is held to it, read under
`firm_scope.firm_of(user)`:

| Who | Ceiling and consent (402) | Licence suspended | Licence ended |
|---|---|---|---|
| subscriber (`manager`, no `firm_id`) | yes | « Mon abonnement » alone | refused |
| colleague (`manager` with `firm_id`) | yes, on the firm's licence | refused | refused |
| platform `admin` | no | no | no |
| investors | register nobody | keep their space | keep their space |

Before 8 November the licence was read on the caller's own id: a colleague, whose id Alice
files no licence under, met a 403 where the subscriber met the ceiling, and a blocked firm
went on working through its colleagues.

## What is counted: ONE function

`license_service.billable_investor_counts` is the only count. It feeds the ceiling and its
402 (`check_investor_quota`), the screen's « 48 / 50 » (`quota_outlook`) and the
`managed_count` sent to Alice (`/internal/managers`, `/internal/managers/{id}`).

- **by the firm that manages**: `investors.firm_id`, stamped with the firm of the account
  that registered the investor, so an investor counts once, whichever colleague typed it;
- **a refused KYC file frees its place**; any other file counts, pending included;
- **reported on the account that IS the firm**: a colleague answers `managed_count = 0`. Every
  account of a firm used to report the firm's whole count, so Alice's list carried it once
  per colleague.

This product has no archive and no exit of an investor: the refusal is the only way a place
is freed. A read-only before/after measurement lives outside the repository:
`C:\Users\Arons\Documents\LeComptoir-mesures\invest_unites_facturees_avant_apres.sql`.

## The doors into the plan

Both go through `license_service.check_investor_quota` (400 when a closed plan is full, 402
consent when the overage is allowed, `accept_overage=true` to confirm), for every account of
the team:

- registration (`POST /investors`);
- reversing a refusal (`POST /investors/{id}/kyc` from `refused` to anything else).

There is no import, duplication or transfer of investors in this product.

The 402 states the count and the price in the subscription's currency (the euro: Invest's
Checkout is asked in euros), read from Alice's `overage_prices` with `overage_price` as the
fallback, written by `core.display.amount` with the currency's decimals in the reader's
language (« 12,50 € », « €12.50 »). On screen, `lib/overage.ts` asks the question and replays
the request; the API client never toasts a 402.

## The licence cache

`alice_client.get_license` keeps a licence Alice answered 60 s per process (it is read on
every request). Alice sends Invest no licence webhook: her `/internal/managers/{id}/block` and
`/unblock` drop the entry, and so does a plan change made through « Mon abonnement ». Another
backend worker keeps its copy until it expires.

## What a blocked licence withdraws

Read from the licence on every request and at every sign-in (`licence_state.gate`, called by
`deps.current_user`, `/auth/login`, the second factor and the password link), never written
into `users.is_active`:

- suspended (unpaid invoice, or blocked by hand): a colleague is refused, 401
  `agency_suspended`; the subscriber signs in and reaches `/api/v1/billing`, `/api/v1/auth/`
  and `/api/v1/terms` alone (`licence_state.HELD_SUBSCRIBER_PREFIXES`), elsewhere 403
  `subscription_suspended`;
- terminated (`access_until` passed, written by Alice on a termination only): the colleagues
  are refused, 401 `licence_ended`; the subscriber is held to « Mon abonnement » exactly as in
  a suspension (the owner, 9 Nov 2026, « oui fais le »): he signs in (password, second factor,
  password link), reads and downloads his invoices and credit notes, settles what is still
  due (card or transfer) and subscribes again; elsewhere 403 `licence_ended`. Before, he was
  refused at every door, « Mon abonnement » included. ONE rule holds the subscriber, whatever
  the reason: `licence_state.gate` answers why he is held (`subscription_suspended` or
  `licence_ended`), `deps.current_user` keeps him to `held_subscriber_may_reach` and
  `held_subscriber_refusal` says why. Proven by
  `test_a_terminated_licence_keeps_the_subscriber_on_his_subscription`;
- 🔴 thirty days to read and export once it ended (terms of sale, article 7.4; the owner,
  12 Nov 2026): for `licence_state.EXPORT_DAYS` (30) days after `access_until`, the
  subscriber of an ended licence is let in freely for every READ (GET and HEAD: the register,
  the exports, the documents; `gate(reading=True)` answers None, so `/auth/me` holds him
  nowhere), writes stay refused (403 `licence_ended`); then « Mon abonnement » alone as
  above. `GET /billing` says `export_until` and `exports_open` and the red banner says
  « jusqu'au …, vous gardez la lecture et l'export de vos données »
  (`subscriptionBanner.endedExports`). Nothing is erased by this product at the end of the
  window: it only closes the reads. The colleagues stay refused from the end. Proven by
  `test_an_ended_subscription_reads_and_exports_for_thirty_days`;
- investors keep their space in both cases (the owner, 8 and 9 November 2026: a closed
  licence leaves the end users their access in every tool, exactly as a suspension does). ONE
  rule says who is held to the licence: the manager accounts (`licence_state.gate`, `role !=
  MANAGER` lets anyone else through). Proven by `test_a_terminated_licence_keeps_its_investors`
  (password sign-in and their space, 200; a colleague 401 `licence_ended`).

The machine code travels in `X-Error-Code`. The client carries a closed firm's sentence to
the sign-in page (`lib/sessionNotice.ts`) on a 401, and sends a held subscriber to `/billing`
without a toast on a 403 `subscription_suspended` or `licence_ended` (the status tells the
team's 401 `licence_ended` from the subscriber's 403); `/auth/me` says
`subscription_suspended` or `subscription_ended` and the router keeps them there.

A new version of the terms, published and not yet in force, is announced on every page during
its notice (terms of use, article 10.1; the owner, 12 Nov 2026): `/terms/status` relays
Alice's `upcoming` (version, product, audience, effective date, what changes; absent or
malformed: null), `components/terms/UpcomingTermsBanner.tsx` says « Nouvelles conditions au
… », « Lire » opens the text announced (`TermsReader` `ahead`), and a version read or hidden
does not come back.

`/internal/managers/{id}/block` switches nobody off and answers an empty `blocked_user_ids`
(it answered `user_ids`, a key Alice does not read: her `unblock` came back with an empty list
and the subscriber it had switched off stayed off). `/unblock` reactivates the listed
accounts and the manager itself when an older block left it off (`/block` was the only writer
of `is_active = false` for a manager). The gate fails open: no console, no licence or an Alice
that does not answer lets the account in.

## What the subscriber is told

`GET /billing` relays the firm's licence and Alice's billing calendar, each key optional:
`billing_starts_on`, `has_payment_method`, `payment_failed_on`, `suspension_on`, plus
`is_holder`, `suspended`, `ended` (the termination has run out) and `unavailable` (Alice
answered neither 200 nor 404). The banner at
the top of the shell (`components/layout/SubscriptionBanner.tsx`, decided by
`lib/subscriptionBanner.ts`) speaks to the licence holder only:

- suspended: red, since when, link to « Mon abonnement »;
- ended: red, « Votre abonnement a pris fin », link « Se réabonner » to « Mon abonnement »,
  where the page says the same above the plans Alice offers to subscribe again (her offer
  answers `mode: subscribe` for a cancelled subscription, 9 Nov 2026);
- a debit failed, still in the grace period: amber, until when to settle;
- billing starts on a coming date, the plan is paid, the account is not a demonstration and
  no payment method is on file: blue, closable for the session.

« Mon abonnement » shows the bank transfer whenever Alice offers it, card or not; an unpaid
invoice offers its way out on its own line (pay, pay by card, declare a transfer); « Actif »
is not shown while a debit has failed; the page says when Alice does not answer. Paying the
plan in place asks the terms of sale and the agreement still owed, checked by the server
before Alice's Checkout; her own 409 (`X-Refusal: terms_cgv` / `terms_dpa`) is said in this
product's words. Billing calls that fail on her key (401/403), her insides (5xx) or the
network answer 503 « Le service de facturation est momentanément indisponible », never her
sentence; a business refusal she wrote for the subscriber is relayed with her status.

🔴 AN ENDED LICENCE PAYS ONE INVOICE, NEVER SUBSCRIBES AGAIN BY PAYING IT (the owner, 9 Nov
2026). On an invoice still due of an ended licence, « Régler » calls
`POST /api/v1/billing/invoices/{invoice_id}/pay`, which relays Alice's
`POST /internal/billing/pay-invoice/{firm}` with the invoice and the page's return addresses
(`PUBLIC_APP_URL/billing?paiement=succes|annule`) and sends the subscriber to the `url` she
answers: a one-off payment of that invoice, or the open invoice of a subscription still
running. Never the Checkout of the plan (which opens a new subscription) nor the portal, and a
payment never reopens a closed licence; subscribing again is the plans' business, above. Her
409 (a transfer declared, awaiting validation) and 400 (nothing left to pay on that invoice)
are said in this product's words, in French and English; the rest as every billing gesture.
Licences active or suspended keep their way out (portal, or the Checkout of the plan).

🔴 BEFORE THE BILLING START NOTHING IS OWED (the owner, 9 November 2026: « À régler », « Payer
mon abonnement » and the transfer details on 9 November in Immo, for a first invoice on
1 January 2027). This page drew no « À régler » for the month, but said « Paiement à mettre
en place », « Payer maintenant » (« Paiement immédiat ») and showed the bank transfer with its
declaration for a month nobody owes. `GET /billing/status` relays Alice's
`current_period_billed` and `billing_starts_on` (LeComptoirAlice, docs/BILLING_CONTRACT.md
« Before the billing start, nothing is owed »), read through `components/billing/billedPeriod.ts`,
the same file in the nine products under the fingerprint of
`billedPeriod.test.ts`. While the month is not billed, the plan reads « Actif », the card button
« Ajouter un moyen de paiement » (Alice's Checkout sets a trial until the start) with « Rien
n'est prélevé avant le début de la facturation, le … » in place of « Paiement immédiat », and
the bank transfer is not offered unless an invoice already issued is still owed (it stays owed,
as before). The next payment is the one Alice's offer announces (`next_due_date`, on the billing
start). An older Alice leaves the field out: the month is billed
(`nothingIsOwedBeforeTheBillingStart.test.ts`).

**One rule for the month in course, in the nine products** (the owner, 10 November 2026: one
need, one code). Whether the current month is billed, whether it is owed, what the plan's
Checkout is offered for, whether the bank details show and which badge the plan wears are
`frontend/src/components/billing/billedPeriod.ts`, the same file in Immo, RH, Compta, PDF,
Séjour, Syndic, BTP, Invest and Market, under the FNV-1a fingerprint `7c14c985` held by
`billedPeriod.test.ts` (the text read with LF line ends): change one, change them all, and the
fingerprint. It replaced `periodBilling.ts` (PDF, Syndic, BTP), the former `billedPeriod.ts`
(Compta, Séjour, Invest, Market) and the rules written in the pages (`owesCurrent` of Immo,
Compta and Invest; RH's `owesCurrentPeriod`, which now reads it). Immo's rule is the model:
the month is owed when billed, not paid, not a demonstration, not held by a running
subscription, at a positive price, the licence not ended; an ended licence subscribes again
and owes only its issued invoices. The page keeps what is its own: whether the card or the
transfer is open, a transfer declared, the terms to tick, and its words. Where this product
differed (10 Nov 2026), Immo's rule now holds: a suspended or ended licence wears its red
badge beside the plan (the notice above stays); « Paiement à mettre en place » is drawn for
the month owed alone (it was the badge of every other case, a free plan included); a plan
whose price Alice does not give owes nothing; an ended demonstration account is offered to
subscribe again.

**A means of payment settled has nothing to add** (the owner, 12 November 2026: « Paie par
virement » ticked on Alice's console for an account billed from 1 January 2027; the banner
« ajoutez un moyen de paiement » went away, « Mon abonnement » still offered « Ajouter un moyen
de paiement », which opened Stripe). The plan held carries Alice's `has_payment_method` of
`/internal/license` (true for a debit Stripe will make or for a payer by transfer, her
decision of 9 November), told, never inferred: before the start, `planCheckoutOf` offers the
Checkout to add a means of payment only when it is not `true` (absent or null: as before), and
`meansSettledBeforeStart` is true for a plan held by no subscription whose means is settled, a
payer by transfer; the page then says « Vous réglez vos factures par virement » instead of the
card. A month owed, an issued invoice left unpaid and an ended licence are unchanged; the
portal stays a subscriber's.

🔴 THE INVOICE STILL TO PAY IS SAID ON EVERY SCREEN (the owner, 9 November 2026: after the
billing start, a subscriber paying by transfer, or with no means of payment, had nothing on
screen between the invoice e-mail and the suspension). Alice serves `invoice_due` in
`/internal/license/{id}` (`number`, `period_year`, `period_month`, `left_ttc`, `currency`,
`due_on`, `overdue`; LeComptoirAlice, docs/BILLING_CONTRACT.md): the oldest invoice still owed,
credit notes deducted, with no transfer declared and no Stripe debit on its way; null when
nothing is to pay, and for a demonstration account. The licence state keeps it as she sends it
(a malformed answer is none) and `api/v1/billing.py (`_as_info`)` relays it. `components/layout/SubscriptionBanner.tsx` tells the holder alone (the
team does not pay): « Votre facture de janvier 2027 (120,00 €) est à régler avant le … » in
blue, closable for the session for THAT invoice; once `overdue`, « Votre facture de … (…) n'est
pas réglée : elle était due le … » in amber, never closable; both link to « Mon abonnement ».
A suspension, an ended subscription and a refused debit go first; « devient payant » shows
before the start only, never beside it (lib/subscriptionBanner.ts; four keys in French and English). The month is in full, without a capital
in French, and the amount in the invoice's currency, in the reader's format, through
`components/billing/invoiceDue.ts`, the same file in Séjour, Invest, Market, Compta, Syndic,
BTP and PDF under the fingerprint of `invoiceDue.test.ts`.

## What is offered is what is owed (the owner's recipe, 9 Nov 2026)

« Tous les cas doivent être gérés »: measured on this page before it was corrected.

- 🔴 A SUBSCRIBER GETS THE PORTAL, NOTHING ELSE. « Changer de moyen de paiement » opened
  Alice's Checkout for a licence holding a running Stripe subscription: a second
  subscription, the licence followed it and the first one kept charging. The Checkout button
  is drawn only for whoever holds no subscription (`payShown` in `pages/Billing.tsx`); a
  subscriber has « Gérer mon abonnement » (`billing/portal`). Alice refuses that Checkout
  anyway (409 `X-Refusal: already_subscribed`, her sentence in French only):
  `api/v1/billing._unavailable` says it in French or English, naming « Gérer mon
  abonnement », as a 409.
- 🔴 « RÉGLER » PAYS THAT INVOICE ALONE, for every licence. It opened the plan's Checkout for
  whoever held no subscription (it subscribed again and charged a proration) and the portal
  for a subscriber (which has nothing to charge for an invoice issued before the card). It
  calls `POST /api/v1/billing/invoices/{invoice_id}/pay` (Alice's `pay-invoice`), which sends
  a subscriber to his own open Stripe invoice and anybody else to a one-off payment of THAT
  invoice; never for a demonstration account.
- 🔴 A MONTH PAID, OR A DEMONSTRATION ACCOUNT, OWES NOTHING (Immo's `owesCurrent`): a payer
  by transfer whose month is paid read « Paiement à mettre en place », « Payer maintenant »,
  the bank details and « J'ai fait le virement » (answered « Aucune facture à régler »).
  `owesCurrentPeriod` of `components/billing/billedPeriod.ts`: billed,
  not paid (`current_period_paid`), not a demo (`is_demo`), not held by a subscription, not
  free (`monthly_price`), the licence not ended. Badges « À jour » and « Compte de
  démonstration, non facturé »; no Checkout button; the bank details only for the month owed
  or an invoice still to pay (never for a demo).

French and English.

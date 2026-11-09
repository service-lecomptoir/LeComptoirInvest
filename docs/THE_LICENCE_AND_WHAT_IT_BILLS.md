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
  and `/api/v1/terms` alone (`licence_state.SUSPENDED_SUBSCRIBER_PREFIXES`), elsewhere 403
  `subscription_suspended`;
- terminated (`access_until` passed, written by Alice on a termination only): the whole team
  is refused, 401 `licence_ended`;
- investors keep their space in both cases.

The machine code travels in `X-Error-Code`. The client carries a closed firm's sentence to
the sign-in page (`lib/sessionNotice.ts`) and sends a suspended subscriber to `/billing`
without a toast; `/auth/me` says `subscription_suspended` and the router keeps them there.

`/internal/managers/{id}/block` switches nobody off and answers an empty `blocked_user_ids`
(it answered `user_ids`, a key Alice does not read: her `unblock` came back with an empty list
and the subscriber it had switched off stayed off). `/unblock` reactivates the listed
accounts and the manager itself when an older block left it off (`/block` was the only writer
of `is_active = false` for a manager). The gate fails open: no console, no licence or an Alice
that does not answer lets the account in.

## What the subscriber is told

`GET /billing` relays the firm's licence and Alice's billing calendar, each key optional:
`billing_starts_on`, `has_payment_method`, `payment_failed_on`, `suspension_on`, plus
`is_holder`, `suspended` and `unavailable` (Alice answered neither 200 nor 404). The banner at
the top of the shell (`components/layout/SubscriptionBanner.tsx`, decided by
`lib/subscriptionBanner.ts`) speaks to the licence holder only:

- suspended: red, since when, link to « Mon abonnement »;
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

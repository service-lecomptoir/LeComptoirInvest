# The space is erased after the export days

The owner, 13 Nov 2026: yes to the erasure once the thirty days have run out. The terms of
sale of Alice (7.4) and the data processing agreement (11): thirty days to read and export
once the subscription has ended, then the data are erased. Alice's side:
`LeComptoirAlice/docs/THE_SPACE_IS_ERASED_AFTER_THE_EXPORT_DAYS.md`; the reference
implementation: Le Comptoir Immo's page of the same name.

## One need, one code

- `app/core/self_delete.py`: the rules every product shares, byte for byte (fingerprint
  checked by `tests_unit/test_the_self_delete_core_is_shared.py`): the calendar
  (`is_due`, `reminder_due`, seven days before), `ended_erase_on`, the launch day.
- `app/services/firm_purge.py`: `purge_firm`, the ONE purge of a subscriber's firm. The
  ended erasure runs it today; « Supprimer mon compte », when this product gets the button,
  runs the same function on the same rows (`account_deletions`).
- `app/services/account_deletion_service.py`: the glue (who is the subscriber, when, whom to
  tell), and the daily pass.

🔴 The console's own deletion (`DELETE /internal/managers/{id}`) runs the same purge
since 14 Nov 2026 (the owner: « la suppression depuis la console suit la purge »): it
removed the account row alone and left the firm's funds, investors, subscriptions, money and team behind, with no holder.
`account_deletion_service.delete_from_console` runs `firm_purge.purge_firm` for the root, the account
alone for any other, journaled by name (`account.console_deletion_executed` with the
numbers, `account.console_deletion_held` with why).

## The holds, said to Alice

One need, one code: `firm_purge.erasure_hold` gathers this product's guards (`shared_rows`: a link to another firm; `platform_account_inside`: a platform account filed under the firm; `last_administrator`)
and names them with the shared core's codes (`core/self_delete.py`, `HOLD_CODES`). The same
answer serves three doors:

- the morning plan says it to Alice (`say_the_holds`, `POST /internal/license/{id}/
  erasure-hold`, a code or `null` when the hold ended), every morning, so an Alice that does
  not answer, or answers 404, hears it the next one; nothing is erased nor blocked by it;
- the day's erasure holds on it (`why_not_erase`), and no notice announces an erasure it
  holds;
- the console's deletion is refused by it: 409, the code in `X-Refusal`, the core's
  sentence; Alice asks `GET /internal/managers/{id}/deletion-hold` first, before she stops
  the Stripe subscription.

A row planned for an account deleted in the meantime is withdrawn
(`account_deleted_from_the_console`), never purged by the pass.

## Who is the subscriber

The account that holds the licence: a `manager` with no `firm_id`
(`User.holds_the_licence`), the id Alice files the licence under (`manager_user_id`). The
firm is that account's id (`core.firm_scope.firm_of`). Never planned: a colleague (`firm_id`
set), an investor account, the platform's `admin`.

## Alice decides, Invest checks

1. Once a day (`account_deletion_service.run_forever`, in process like the audit
   retention; an advisory lock lets one of the two workers work; only when a console drives
   this instance), `plan_ended` reads Alice's list (`/internal/erasures?product=invest`). A
   subscriber she lists gets a row at the later of her day and Invest's own reading of the
   same end (`self_delete.ended_erase_on`: the day after the platform's last day of the
   thirty days, never before `FIRST_ERASURE_DAY`). A row she no longer lists is withdrawn
   (`account.erasure_withdrawn`). Alice not answering plans and withdraws nothing.
2. On the day (the platform's day AND the holder's, `holder_today`, from the account's
   country), the erasure runs only for an account Alice LISTS that very morning, and only
   when `why_not_erase` finds nothing: Alice answers AGAIN, without the cache
   (`alice_client.fresh_licence`), that the licence is not a demonstration (said,
   `is_demo: false`), that it ended, with a day scheduled and reached, like Invest's own;
   nothing of the firm is linked to another firm (`firm_purge.shared_with_another_space`,
   every foreign key between the purged tables, and an investor's sign-in account); no
   platform account hangs from the firm; and another active account can still administer
   the installation. Anything else holds the erasure (`account.erasure_held`, with why) and
   asks again the next morning.
3. Then the purge, `account.erasure_executed` with the numbers (accounts, funds, investors,
   subscriptions, projects, bank movements, contributions, distributions, investor
   documents), never a name; then Alice, `cause: subscription_ended` and the numbers
   (`/internal/license/{id}/account-deleted`); she keeps every invoice. Alice unreachable:
   the row stays « Alice à prévenir » and the next pass tells her, never purging twice.
4. Seven days before, the notice to the holder, in their language (`User.locale`, French or
   English, the two languages of this product), dressed in the firm's look, once per day
   planned (a day moved by Alice gets its own notice; a notice not sent is tried again the
   next morning).

The notice is written like this product's other letters (the password link): there is no
library of editable letters in Invest. 🔴 This product has NO page that exports a firm's
data: the notice's button opens the register of the investors (`/investors`), the nearest
screen, and the letter says « consulter », never « exporter ».

## What is erased, what is kept

Erased, in one transaction, leaves first (`PURGE_ORDER`): the four tables that carry the firm
(`firm_scope.SCOPED_TABLES`: funds, investors, projects, bank movements), read off
`firm_id`, and every table below them, reached through its foreign keys to those four
(`firm_purge.owned`, built from the models' keys): subscriptions, their requests and
conversions, capital calls, contributions, distributions, deployments, project returns and
valuations, the investors' KYC pieces; then every account of the firm (colleagues and
investor accounts, `users.firm_id`) with its second factor, then the holder. Bulk deletes:
the journal's listeners would otherwise copy the rows erased (names, addresses, IBAN
fingerprints) into the journal. A guard (`tests_unit/test_the_purge_erases_every_table_of_a_firm.py`)
makes every table of the schema say whether it is purged, kept or an account table, and
checks the order against the foreign keys.

Kept: the audit journal (its own retention, ninety days), the closed sessions
(`revoked_sessions`: an id and an expiry, gone by themselves), the `account_deletions` row (no
personal data), and at Alice every subscription invoice. No file: this product keeps none on
disk (its only volume is the database's; a statement is drawn on demand). A copy remains in
the backups until their rotation.

## The launch

`core/self_delete.ERASURE_LAUNCH_DAY = 2026-11-20`, `FIRST_ERASURE_DAY = 2026-12-20`. A
subscriber whose thirty days had run out gets `FIRST_ERASURE_DAY`, the notice on 13 Dec
2026, and reads until the eve (`licence_state.export_until`, only when Alice schedules the
erasure).

## On screen

- The banner of an ended subscription: « … jusqu'au JJ/MM/AAAA … Vos données seront
  effacées le JJ/MM/AAAA. » (`lib/subscriptionBanner.endedWords`, `GET /billing` says
  `erase_on`).
- The banners' days are JJ/MM/AAAA in both languages (`bannerDay`, the product's one
  formatter `lib/format.day` with the pattern `dd/MM/yyyy`): the thirty days, the erasure,
  the new terms.
- A write during the thirty days: 403 `subscription_read_only`, « Abonnement terminé :
  lecture et export seulement jusqu'au JJ/MM/AAAA » in the reader's language, said by a
  message with « Mon abonnement » a click away; the form stays open with what was typed.
  « Mon abonnement », the sign-in and the terms still take a write. After the thirty days,
  the confinement to « Mon abonnement » is unchanged.

## Measuring

`LeComptoir-mesures/effacements_a_venir_inv.sql` (read-only): for the accounts Alice's own
script lists, the firm's name and what the erasure would take, the links to another firm
that would hold it, the administrators left, the rows a console deletion left without a
holder, and the rows already planned.

## Tests

`backend/tests/test_the_space_is_erased_after_the_export_days.py`,
`backend/tests/test_an_ended_subscription_reads_and_exports_for_thirty_days.py`,
`backend/tests/test_the_console_deletion_follows_the_purge.py`,
`backend/tests_unit/test_the_self_delete_core_is_shared.py`,
`backend/tests_unit/test_the_purge_erases_every_table_of_a_firm.py`,
`frontend/src/lib/theSpaceIsErasedAfterTheExportDays.test.ts`.

"""Paying the investors: who is served, in what order, and what stops the payment.

🔴 THIS IS WHERE `DISTRIBUTION_ORDER` FINALLY DOES SOMETHING. Until this module the fund
could take money in, deploy it and collect returns, but it could not pay anyone — the
fourth movement was a table and a constant with no code between them. A tool that tracks
three of the four movements reconciles beautifully right up to the day it has to pay.

THE ORDER IS NOT THE GUARD. `instruments` says it in as many words: distributing to
subscribers the cash owed on a lender's next instalment does not merely reorder anything,
it CAUSES the default. So this module does two separate things, and the second is the one
that matters:

  1. it SERVES lenders first, pro rata among them when there is not enough;
  2. it REFUSES to give subscribers anything while any lender remains owed.

Rule 1 alone would still let a fund pay its members and default the same afternoon: an
ordering only decides who gets the money that IS distributed, and the amount distributed is
chosen by a human. Rule 2 is what makes the ordering mean something.

⚠️ AND WHAT CANNOT BE COMPUTED BLOCKS EVERYTHING. If one loan's due amount is unknown —
amortising with no schedule recorded, or terms missing — then « are the lenders covered »
has no answer, and a proposal that skipped it would present subscribers as safely payable
on the strength of a debt nobody measured. The refusal names the loan.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import accrual, instruments, money
from app.core.instruments import EquityTerms, LoanTerms
from app.models.fund import Fund
from app.models.investor import Investor
from app.models.subscription import Subscription
from app.models.treasury import OUT, BankMovement, Contribution, Distribution
from app.core.i18n import pick


@dataclass(frozen=True)
class Share:
    """One investor's share of one distribution, split the way their statement needs it."""

    subscription_id: uuid.UUID
    investor_id: uuid.UUID
    investor_name: str
    instrument: str
    capital_amount: Decimal
    income_amount: Decimal
    currency: str

    @property
    def gross_amount(self) -> Decimal:
        return self.capital_amount + self.income_amount


@dataclass(frozen=True)
class Waterfall:
    """A proposed distribution: who gets what, what is still owed, and what blocks it."""

    currency: str
    available: Decimal
    as_of: date
    shares: list[Share] = field(default_factory=list)
    #: What lenders are still owed once these shares are paid. Zero means covered.
    debt_remaining: Decimal = Decimal("0")
    #: Set when subscribers were served NOTHING because lenders are not covered, or when
    #: nothing at all can be proposed. Never empty when the two disagree with the intent.
    blocked_reason: str | None = None
    #: Loans whose due amount could not be computed, with the reason. Non-empty means the
    #: whole proposal is refused: `shares` is empty and `blocked_reason` is set.
    unknown: list[tuple[uuid.UUID, str]] = field(default_factory=list)

    #: 🔴 THE MANAGER'S SHARE, HELD APART FROM `shares` AND DELIBERATELY SO. Carried interest
    #: is not a distribution to an investor: it has no subscription, no investor tax
    #: statement, and folding it into a share would make the manager appear in the register
    #: as a holder they are not. It is shown separately because an amount that leaves the
    #: subscribers' pocket must be read, never inferred.
    carried_interest: Decimal = Decimal("0")
    #: The preferred return still to be served to subscribers after this proposal. Zero means
    #: the hurdle is met and carried interest has begun.
    preferred_remaining: Decimal = Decimal("0")
    #: 🔴 THE MANAGEMENT FEE TAKEN OUT OF THIS DISTRIBUTION, held apart from the carry and
    #: from the shares. It is a COST OF RUNNING the vehicle, owed whether the fund performs
    #: or not; folding it into the carry would tell subscribers the manager earned nothing in
    #: a flat year while they had been paying all along.
    management_fee: Decimal = Decimal("0")

    @property
    def distributed(self) -> Decimal:
        """What leaves the fund: the investors' shares, the carry AND the management fee.

        ⚠️ BOTH OF THE MANAGER'S AMOUNTS ARE PART OF IT. Leaving either out would show money
        actually allocated to the manager as « kept by the fund », and the undistributed
        balance would be wrong by exactly the amount nobody is looking at.
        """
        return (
            sum((s.gross_amount for s in self.shares), Decimal("0"))
            + self.carried_interest
            + self.management_fee
        )

    @property
    def undistributed(self) -> Decimal:
        """What the fund keeps. Shown, never hidden: cash that stayed is a decision."""
        return self.available - self.distributed


@dataclass
class _Holding:
    """One open subscription with everything already known about it. Internal."""

    subscription: Subscription
    investor: Investor
    contributed: Decimal
    capital_repaid: Decimal
    income_paid: Decimal
    due: accrual.Due | None = None
    #: First day the money arrived. The preferred return runs from there, never from the
    #: signature: a subscriber who has not paid in yet was deprived of nothing.
    drawn_on: date | None = None

    @property
    def capital_at_work(self) -> Decimal:
        return self.contributed - self.capital_repaid


async def _holdings(
    db: AsyncSession, currency: str, as_of: date, fund_id: uuid.UUID | None = None
) -> list[_Holding]:
    """Every open subscription in one currency, with what has been paid in and back out.

    ⚠️ « ALREADY SERVED » COUNTS DECIDED DISTRIBUTIONS, NOT ONLY PAID ONES, and that is a
    deliberate difference from `portfolio_service`. The two answer different questions: an
    investor's statement shows what they RECEIVED, so it counts what left the account; a new
    proposal must not re-allocate what a previous decision already gave them, so it counts
    what was DECIDED. Using the paid figure here would propose the same coupon twice for as
    long as the first one sat unpaid, and the second proposal would look perfectly sound.
    """
    subscriptions = (
        (
            await db.execute(
                select(Subscription)
                .where(
                    Subscription.currency == currency,
                    Subscription.converted_on.is_(None),
                    # 🔴 THE VEHICLE IS PART OF THE SCOPE, and NULL is a scope of its own.
                    # `== None` would be a comparison SQLAlchemy turns into `IS NULL`, which
                    # is what we want; written explicitly so nobody « fixes » it into an
                    # equality that silently matches nothing.
                    Subscription.fund_id.is_(fund_id)
                    if fund_id is None
                    else Subscription.fund_id == fund_id,
                )
                .order_by(Subscription.signed_on)
            )
        )
        .scalars()
        .all()
    )
    if not subscriptions:
        return []
    ids = [s.id for s in subscriptions]

    contributed: dict[uuid.UUID, Decimal] = {}
    first_drawn: dict[uuid.UUID, date] = {}
    for sub_id, amount, movement_date in (
        await db.execute(
            select(
                Contribution.subscription_id,
                Contribution.amount,
                BankMovement.value_date,
            )
            .join(BankMovement, BankMovement.id == Contribution.bank_movement_id)
            .where(Contribution.subscription_id.in_(ids))
        )
    ).all():
        contributed[sub_id] = contributed.get(sub_id, Decimal("0")) + amount
        known = first_drawn.get(sub_id)
        if known is None or movement_date < known:
            first_drawn[sub_id] = movement_date

    repaid: dict[uuid.UUID, Decimal] = {}
    income: dict[uuid.UUID, Decimal] = {}
    for sub_id, capital, earned in (
        await db.execute(
            select(
                Distribution.subscription_id,
                Distribution.capital_amount,
                Distribution.income_amount,
            ).where(Distribution.subscription_id.in_(ids))
        )
    ).all():
        repaid[sub_id] = repaid.get(sub_id, Decimal("0")) + (capital or Decimal("0"))
        income[sub_id] = income.get(sub_id, Decimal("0")) + (earned or Decimal("0"))

    investors = {
        i.id: i
        for i in (
            await db.execute(
                select(Investor).where(
                    Investor.id.in_({s.investor_id for s in subscriptions})
                )
            )
        )
        .scalars()
        .all()
    }

    out: list[_Holding] = []
    for s in subscriptions:
        holding = _Holding(
            subscription=s,
            investor=investors[s.investor_id],
            contributed=contributed.get(s.id, Decimal("0")),
            capital_repaid=repaid.get(s.id, Decimal("0")),
            income_paid=income.get(s.id, Decimal("0")),
            drawn_on=first_drawn.get(s.id, s.signed_on),
        )
        if s.instrument == instruments.LOAN:
            holding.due = accrual.amount_due(
                terms=_loan_terms(s.terms),
                principal_contributed=holding.contributed,
                currency=currency,
                # ⚠️ INTEREST RUNS FROM THE DAY THE MONEY ARRIVED, not from the signature.
                # A loan signed in January and drawn in April owes three months less, and
                # the lender was not deprived of anything in between.
                drawn_on=first_drawn.get(s.id, s.signed_on),
                matures_on=s.ends_on,
                as_of=as_of,
                interest_already_paid=holding.income_paid,
                capital_already_repaid=holding.capital_repaid,
            )
        out.append(holding)
    return out


def _loan_terms(raw: dict | None) -> LoanTerms | None:
    """Rebuild the terms from stored JSON, keeping only what the dataclass declares.

    ⚠️ UNKNOWN KEYS ARE DROPPED, NEVER PASSED THROUGH. The sister product learnt this the
    expensive way: a schema that silently swallowed a field it did not name produced NaN in
    production. Here the opposite risk applies — an extra key would raise — so the filter is
    explicit and the omission is visible in this one place.
    """
    if not raw:
        return None
    allowed = LoanTerms.__dataclass_fields__.keys()
    return LoanTerms(**{k: v for k, v in raw.items() if k in allowed})


def _equity_terms(raw: dict | None) -> EquityTerms:
    """A subscription's terms, or those of a fund that takes nothing.

    ⚠️ ABSENCE MEANS « NEITHER HURDLE NOR CARRY », and it is the one acceptable default
    here: zero and zero reproduce exactly the waterfall that existed before this module,
    where every surplus goes to the subscribers. A fund that recorded nothing is therefore
    never given a manager's fee it did not agree to, and a crowdfunding vehicle, which has
    none, has nothing to fill in.
    """
    if not raw:
        return EquityTerms()
    allowed = EquityTerms.__dataclass_fields__.keys()
    return EquityTerms(**{k: v for k, v in raw.items() if k in allowed})


def _shared_equity_terms(
    equity: list[_Holding], fund: Fund | None = None
) -> tuple[EquityTerms | None, str | None]:
    """The terms that govern this distribution, or the reason to refuse.

    🔴 A HURDLE AND A CARRY ARE THE FUND'S ECONOMICS, NOT ONE INVESTOR'S. The carry is
    computed on EVERYBODY'S surplus at once, so two subscribers carrying different rates do
    not describe two contracts — they describe a waterfall with no single answer.

    🔴 AND THE VEHICLE NOW ANSWERS. Until it existed, these terms lived on each subscription
    because that is where a terms column happened to be, and this function had to refuse
    whenever two subscribers disagreed — a refusal that was correct and that NOBODY COULD
    RESOLVE, since no object held the fund's own agreement. When a fund states its terms they
    govern, and the disagreement stops being a dead end.

    ⚠️ WITHOUT A FUND IT STILL REFUSES RATHER THAN AVERAGES. Taking the first rate, or the
    mean, or the lowest, would produce a plausible and wrong number, and the gap would come
    out of somebody's share.
    """
    if not equity:
        return None, None

    if fund is not None and fund.terms:
        # The vehicle's own agreement. It does not merely win a tie: it is the statement the
        # subscribers signed up to, and a per-subscription copy is at best an echo of it.
        return _equity_terms(fund.terms), None
    # 🔴 EVERY ECONOMIC TERM IS COMPARED, NOT A CHOSEN FEW. A tuple that named only two of
    # the three silently dropped the management fee: the rebuilt terms carried a fee of zero,
    # the waterfall took nothing, and no test of the fee itself would have caught it because
    # the arithmetic was right — it was the reconstruction that lost the field. Deriving the
    # tuple from the dataclass means a term added later is compared without anyone
    # remembering to come back here.
    _FIELDS = tuple(EquityTerms.__dataclass_fields__)
    distinct = {
        tuple(getattr(t, name) for name in _FIELDS)
        for t in (_equity_terms(h.subscription.terms) for h in equity)
    }
    if len(distinct) > 1:
        readable = " ; ".join(
            ", ".join(f"{name} {value:.2%}" for name, value in zip(_FIELDS, values))
            for values in sorted(distinct)
        )
        return None, pick(
            f"Les souscripteurs ne portent pas les mêmes conditions ({readable}). Une "
            f"cascade par classe de parts n'est pas calculée ici : tant que les conditions "
            f"divergent, aucune répartition n'est proposée.",
            f"The subscribers do not carry the same terms ({readable}). A waterfall by share "
            f"class is not computed here: while the terms differ, no split is proposed.",
        )
    return EquityTerms(**dict(zip(_FIELDS, distinct.pop()))), None


async def propose(
    db: AsyncSession,
    *,
    currency: str,
    amount: Decimal,
    as_of: date,
    fund_id: uuid.UUID | None = None,
    repay_capital: bool = False,
) -> Waterfall:
    """Who gets what out of `amount`, and what stops it.

    `repay_capital` is the fund saying which KIND of distribution this is, and the tool does
    not infer it: paying out a year's profits while the capital stays at work, and winding a
    project down by giving the capital back, are two different acts that look identical from
    the amount alone. Guessing would mislabel capital as income on somebody's tax statement,
    and the investor cannot detect it from the figure they receive.
    """
    fund = await db.get(Fund, fund_id) if fund_id is not None else None
    holdings = await _holdings(db, currency, as_of, fund_id)
    if not holdings:
        return Waterfall(
            currency=currency,
            available=amount,
            as_of=as_of,
            blocked_reason=pick(
                f"Aucune souscription ouverte en {currency}.",
                f"No open subscription in {currency}.",
            ),
        )

    unknown = [
        (h.subscription.id, h.due.unavailable_reason)
        for h in holdings
        if h.due is not None and not h.due.is_known
    ]
    if unknown:
        return Waterfall(
            currency=currency,
            available=amount,
            as_of=as_of,
            unknown=unknown,
            blocked_reason=pick(
                f"{len(unknown)} prêt(s) dont le montant dû n'est pas calculable : tant "
                f"qu'il ne l'est pas, « les prêteurs sont-ils couverts » n'a pas de "
                f"réponse, et rien ne peut être proposé aux souscripteurs.",
                f"{len(unknown)} loan(s) whose amount due cannot be measured: until it is, "
                f"« are the lenders covered » has no answer, and nothing can be proposed to "
                f"the subscribers.",
            ),
        )

    loans = [h for h in holdings if h.subscription.instrument == instruments.LOAN]
    equity = [h for h in holdings if h.subscription.instrument == instruments.EQUITY]
    shares: dict[uuid.UUID, list[Decimal]] = {}  # subscription_id -> [capital, income]

    def give(holding: _Holding, capital: Decimal, income: Decimal) -> None:
        row = shares.setdefault(holding.subscription.id, [Decimal("0"), Decimal("0")])
        row[0] += capital
        row[1] += income

    remaining = amount

    # ---- 1. Lenders, interest before capital -------------------------------------------
    # Interest first even at maturity: it is the older debt, and a lender served capital
    # while their coupon goes unpaid is a lender the fund still owes.
    for field_index, extract in ((1, lambda d: d.interest), (0, lambda d: d.capital)):
        owed = [extract(h.due) for h in loans]
        wanted = sum(owed, Decimal("0"))
        if wanted <= 0 or remaining <= 0:
            continue
        payable = min(remaining, wanted)
        # Pari passu among creditors of the same rank: when there is not enough, everyone
        # is short in the same proportion. Serving them in date order would prefer one
        # lender over another, which no clause here grants.
        parts = accrual.allocate(payable, owed, currency)
        for holding, part in zip(loans, parts):
            if field_index == 1:
                give(holding, Decimal("0"), part)
            else:
                give(holding, part, Decimal("0"))
        remaining -= payable

    served = {
        h.subscription.id: shares.get(h.subscription.id, [Decimal("0"), Decimal("0")])
        for h in loans
    }
    debt_total = sum((h.due.total for h in loans), Decimal("0"))
    debt_paid = sum((v[0] + v[1] for v in served.values()), Decimal("0"))
    debt_remaining = debt_total - debt_paid

    blocked: str | None = None
    carried = Decimal("0")
    management_fee = Decimal("0")
    preferred_remaining = Decimal("0")

    # ---- 2. Subscribers, and only once the lenders are whole ---------------------------
    if debt_remaining > 0:
        # 🔴 THE GUARD, and the reason the ordering is worth anything. Not « subscribers
        # come second »: subscribers come after the debt is COVERED, because paying them out
        # of the cash owed on the next instalment is what causes the default.
        blocked = pick(
            f"Les prêteurs restent dus de {debt_remaining} {currency} : aucune somme ne "
            f"peut aller aux souscripteurs tant que cette dette n'est pas couverte.",
            f"The lenders are still owed {debt_remaining} {currency}: nothing can go to the "
            f"subscribers while that debt stands.",
        )
    elif remaining > 0 and equity:
        weights = [h.capital_at_work for h in equity]
        terms, disagreement = _shared_equity_terms(equity, fund)
        if sum(weights, Decimal("0")) <= 0:
            blocked = pick(
                "Aucun souscripteur n'a de capital au travail : il n'y a rien à répartir "
                "au prorata.",
                "No subscriber has capital at work: there is nothing to split pro rata.",
            )
        elif disagreement is not None:
            blocked = disagreement
        else:
            # ---- 2a. Return of capital, when this distribution is a wind-down ----------
            # Capital back first, then what exceeds it is a gain. The European order, and
            # the one that keeps a wind-down from being reported as performance.
            if repay_capital:
                capital_wanted = sum(weights, Decimal("0"))
                capital_payable = min(remaining, capital_wanted)
                for holding, part in zip(
                    equity, accrual.allocate(capital_payable, weights, currency)
                ):
                    give(holding, part, Decimal("0"))
                remaining -= capital_payable

            # ---- 2a bis. The management fee, before anything is measured against a hurdle
            # 🔴 A FEE IS NOT A CARRY, AND IT COMES FIRST. The carry pays for performance and
            # is earned only above the hurdle; the fee pays for running the vehicle and is
            # owed on a flat year exactly as on a good one. Taking it after the hurdle would
            # make a bad year cost the manager nothing and a good one pay them twice.
            if terms.management_fee > 0 and remaining > 0:
                owed_fee = sum(
                    (
                        accrual.management_fee_accrued(
                            capital_at_work=h.capital_at_work,
                            rate=terms.management_fee,
                            since=h.drawn_on or h.subscription.signed_on,
                            until=as_of,
                            currency=currency,
                        )
                        for h in equity
                    ),
                    Decimal("0"),
                )
                if owed_fee > 0:
                    management_fee = money.quantize(min(remaining, owed_fee), currency)
                    remaining -= management_fee

            # ---- 2b. The preferred return, before the manager takes anything -----------
            # 🔴 THE HURDLE IS A THRESHOLD, NOT A DEBT. Nothing below is owed if the fund
            # earned nothing; what it decides is WHO the next euro belongs to. Skipping it —
            # which is what this module did until now — hands the manager a carry on profits
            # the subscribers were promised first.
            owed_preference = [
                accrual.preferred_return_accrued(
                    capital_at_work=h.capital_at_work,
                    rate=terms.preferred_return,
                    since=h.drawn_on or h.subscription.signed_on,
                    until=as_of,
                    currency=currency,
                    already_served=h.income_paid,
                )
                for h in equity
            ]
            wanted_preference = sum(owed_preference, Decimal("0"))
            if wanted_preference > 0 and remaining > 0:
                payable = min(remaining, wanted_preference)
                # Pari passu among subscribers: short money shortens everyone alike, and no
                # clause here grants one subscriber their preference ahead of another.
                for holding, part in zip(
                    equity, accrual.allocate(payable, owed_preference, currency)
                ):
                    give(holding, Decimal("0"), part)
                remaining -= payable
                preferred_remaining = wanted_preference - payable

            # ---- 2c. Carried interest on what exceeds the hurdle ----------------------
            # ⚠️ ONLY ON THE EXCESS, and only once the preference is fully served. A carry
            # taken on the first euro is a management fee wearing a performance fee's name:
            # the manager would be paid on money that merely came back, and the subscribers
            # would read it as a share of a gain that did not happen.
            if (
                remaining > 0
                and preferred_remaining <= 0
                and terms.carried_interest > 0
            ):
                carried = money.quantize(
                    remaining * Decimal(str(terms.carried_interest)), currency
                )
                if carried > remaining:
                    carried = remaining
                remaining -= carried

            # ---- 2d. The rest, pro rata to capital at work -----------------------------
            if remaining > 0:
                for holding, part in zip(
                    equity, accrual.allocate(remaining, weights, currency)
                ):
                    give(holding, Decimal("0"), part)
                remaining = Decimal("0")

    by_id = {h.subscription.id: h for h in holdings}
    built = [
        Share(
            subscription_id=sub_id,
            investor_id=by_id[sub_id].investor.id,
            investor_name=by_id[sub_id].investor.display_name,
            instrument=by_id[sub_id].subscription.instrument,
            capital_amount=money.quantize(row[0], currency),
            income_amount=money.quantize(row[1], currency),
            currency=currency,
        )
        for sub_id, row in shares.items()
        if row[0] + row[1] > 0
    ]
    built.sort(
        key=lambda s: (instruments.distribution_rank(s.instrument), s.investor_name)
    )
    return Waterfall(
        currency=currency,
        available=amount,
        as_of=as_of,
        shares=built,
        debt_remaining=debt_remaining,
        blocked_reason=blocked,
        carried_interest=carried,
        management_fee=management_fee,
        preferred_remaining=preferred_remaining,
    )


async def record(
    db: AsyncSession,
    waterfall: Waterfall,
    *,
    decided_on: date,
    withholding: dict[uuid.UUID, Decimal] | None = None,
) -> list[Distribution]:
    """Turn a proposal into decided distributions. DECIDED, never paid.

    🔴 `paid_on` STAYS EMPTY. A decision and a payment are two facts, and the gap between
    them is real: the transfer is prepared, sometimes rejected, sometimes sent days later.
    A row that recorded both at once would tell an investor they had been paid on the day
    somebody clicked, and the fund's balance would disagree with its bank.
    """
    if waterfall.unknown:
        raise ValueError(waterfall.blocked_reason or "Proposition incalculable.")
    withheld = withholding or {}
    created: list[Distribution] = []
    for share in waterfall.shares:
        distribution = Distribution(
            subscription_id=share.subscription_id,
            capital_amount=share.capital_amount,
            income_amount=share.income_amount,
            currency=share.currency,
            decided_on=decided_on,
            withholding_amount=withheld.get(share.subscription_id, Decimal("0")),
        )
        db.add(distribution)
        created.append(distribution)
    await db.flush()
    return created


async def pay(
    db: AsyncSession,
    *,
    distribution: Distribution,
    movement: BankMovement,
    paid_on: date | None = None,
) -> Distribution:
    """Attach the outgoing transfer that actually paid this distribution.

    ⚠️ THE SAME THREE CHECKS AS EVERY OTHER ATTRIBUTION, and for the same reason: a
    distribution imputed on an incoming transfer balances the treasury by counting one euro
    twice in opposite directions, and the total looks right.
    """
    if movement.direction != OUT:
        raise ValueError(
            pick(
                "Une distribution s'impute sur un virement SORTANT : ce mouvement est une "
                "entrée.",
                "A distribution is attributed to an OUTGOING transfer: this movement is an "
                "incoming one.",
            )
        )
    if movement.currency != distribution.currency:
        raise ValueError(
            pick(
                f"Le virement est en {movement.currency} et la distribution en "
                f"{distribution.currency}. Une conversion est un événement daté, à un "
                f"cours donné.",
                f"The transfer is in {movement.currency} and the distribution in "
                f"{distribution.currency}. A conversion is a dated event, at a stated rate.",
            )
        )
    if distribution.paid_on is not None:
        raise ValueError(
            pick(
                "Cette distribution est déjà payée.",
                "This distribution has already been paid.",
            )
        )

    already = (
        await db.execute(
            select(Distribution.capital_amount, Distribution.income_amount).where(
                Distribution.bank_movement_id == movement.id
            )
        )
    ).all()
    used = sum((c + i for c, i in already), Decimal("0"))
    if distribution.net_paid > movement.amount - used:
        raise ValueError(
            pick(
                f"Ce virement ne porte plus que {movement.amount - used} "
                f"{movement.currency} à imputer, et {distribution.net_paid} sont demandés.",
                f"This transfer has only {movement.amount - used} {movement.currency} left "
                f"to attribute, and {distribution.net_paid} is being asked for.",
            )
        )

    distribution.bank_movement_id = movement.id
    distribution.paid_on = paid_on or movement.value_date
    await db.flush()
    return distribution


async def owed_to_lenders(
    db: AsyncSession, *, currency: str, as_of: date, fund_id: uuid.UUID | None = None
) -> tuple[Decimal, list[tuple[uuid.UUID, str]]]:
    """What the fund owes its lenders right now, and what it could not measure.

    Read by the treasury screen so the fund sees its debt beside its cash. A balance shown
    without the debt it already carries is the figure that gets distributed.
    """
    holdings = await _holdings(db, currency, as_of, fund_id)
    loans = [h for h in holdings if h.subscription.instrument == instruments.LOAN]
    unknown = [
        (h.subscription.id, h.due.unavailable_reason)
        for h in loans
        if h.due is not None and not h.due.is_known
    ]
    total = sum(
        (h.due.total for h in loans if h.due is not None and h.due.is_known),
        Decimal("0"),
    )
    return total, unknown


__all__ = [
    "Share",
    "Waterfall",
    "owed_to_lenders",
    "pay",
    "propose",
    "record",
]

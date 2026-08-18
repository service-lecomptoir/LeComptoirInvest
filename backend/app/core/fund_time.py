"""Whose day is it. Every date this product records answers that question first.

🔴 `date.today()` ANSWERS THE CONTAINER'S TIME ZONE, which is UTC in production and whatever
a laptop says in development. It is nobody's day: not the fund's, not the investor's. Every
bare call therefore skips a decision — WHOSE day is this — and the skipped decision is
exactly the one that costs something the day the fund crosses a border.

⚠️ AND IT NOW DECIDES MORE THAN IT USED TO. Since the eligibility and chasing work, a date
settles whether a KYC acceptance has expired, whether a capital call is late, and when a
retail investor's reflection period ends. An investor in Réunion asking at 23:00 local time
is recorded on the previous day in UTC — and their four days start a day early, which is a
protection quietly shortened.

TWO ANSWERS EXIST, AND PICKING ONE IS THE POINT:

    platform_today()          the FUND's own day: when the fund acted.
    today_for_investor(...)   the INVESTOR's day: when they acted.

The sister product needed four of these and learnt the rule the expensive way. This one has
two because it has one fund; the boundary is the same, and it is named rather than implied.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

#: The fund's own clock. Stated rather than implied: a product whose scheduler fires on one
#: zone and whose dates are recorded on another disagrees with itself twice a day.
PLATFORM_TIMEZONE = "Europe/Paris"
PLATFORM_ZONE = ZoneInfo(PLATFORM_TIMEZONE)

#: Where an investor's day is, by country. Deliberately SHORT and deliberately incomplete:
#: a country absent from here falls back to the fund's own zone, which is a stated default
#: rather than a wrong guess. Adding a country is one line, and it is a decision somebody
#: takes on purpose.
#:
#: ⚠️ A COUNTRY SPANNING SEVERAL ZONES IS NOT IN HERE, and must not be: picking one of
#: France's twelve for « FR » would be right in Paris and wrong in Cayenne, which is worse
#: than the honest fallback because it looks considered.
_ZONE_BY_COUNTRY: dict[str, str] = {
    "FR": "Europe/Paris",
    "BE": "Europe/Brussels",
    "LU": "Europe/Luxembourg",
    "CH": "Europe/Zurich",
    "PT": "Europe/Lisbon",
    "ES": "Europe/Madrid",
    "IT": "Europe/Rome",
    "DE": "Europe/Berlin",
    "GB": "Europe/London",
    "CI": "Africa/Abidjan",
    "SN": "Africa/Dakar",
    "MA": "Africa/Casablanca",
    "RE": "Indian/Reunion",
    "MQ": "America/Martinique",
    "GP": "America/Guadeloupe",
    "GF": "America/Cayenne",
    "YT": "Indian/Mayotte",
    "PF": "Pacific/Tahiti",
    "NC": "Pacific/Noumea",
}


def platform_today() -> date:
    """The fund's own day, for what no investor owns.

    Deliberately not `date.today()`: UTC is a deployment detail, not an answer. When the
    fund records that IT acted — a decision taken, a valuation entered, a call issued — this
    is the day, and it is the same clock any scheduler would fire on.
    """
    return datetime.now(PLATFORM_ZONE).date()


def zone_for_country(country_code: str | None) -> str:
    """The IANA zone of a country, the fund's own when it is unknown or ambiguous."""
    if not country_code:
        return PLATFORM_TIMEZONE
    return _ZONE_BY_COUNTRY.get(country_code.strip().upper(), PLATFORM_TIMEZONE)


def today_for_investor(country_code: str | None) -> date:
    """The day where THIS investor stands.

    🔴 USED WHERE THE INVESTOR ACTED, never where the fund did. A subscription request is
    theirs: it is what starts their reflection period, and dating it by the server's zone
    can shorten that protection by a day for anybody east or west of the fund. A KYC verdict,
    by contrast, is the fund's act and takes the fund's day.
    """
    return datetime.now(ZoneInfo(zone_for_country(country_code))).date()


__all__ = [
    "PLATFORM_TIMEZONE",
    "PLATFORM_ZONE",
    "platform_today",
    "today_for_investor",
    "zone_for_country",
]

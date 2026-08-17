"""Every model, imported here so `Base.metadata` knows the whole schema.

A model that no module imports is a table that `create_all` does not build and that
autogenerate proposes to DROP. One import list, in one place.
"""

from app.models.base import Base
from app.models.investor import Investor, InvestorDocument
from app.models.subscription import (
    Subscription,
    SubscriptionConversion,
    SubscriptionRequest,
)
from app.models.user import User

__all__ = [
    "Base",
    "Investor",
    "InvestorDocument",
    "Subscription",
    "SubscriptionConversion",
    "SubscriptionRequest",
    "User",
]

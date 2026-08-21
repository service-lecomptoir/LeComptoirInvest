"""Every model, imported here so `Base.metadata` knows the whole schema.

A model that no module imports is a table that `create_all` does not build and that
autogenerate proposes to DROP. One import list, in one place.
"""

from app.models.base import Base

# ⚠️ `Fund` WAS MISSING FROM THIS LIST, which the header of this very file calls
# dangerous: a model no module imports is a table `create_all` does not build and that
# autogenerate proposes to DROP. Noticed on 21 August while installing the per-firm
# scope, which needs the class.
from app.models.fund import Fund
from app.models.investor import Investor, InvestorDocument
from app.models.project import Deployment, Project, ProjectReturn
from app.models.subscription import (
    Subscription,
    SubscriptionConversion,
    SubscriptionRequest,
)
from app.models.treasury import (
    BankMovement,
    CapitalCall,
    Contribution,
    Distribution,
)
from app.models.user import User

__all__ = [
    "BankMovement",
    "Base",
    "CapitalCall",
    "Contribution",
    "Deployment",
    "Distribution",
    "Investor",
    "Fund",
    "InvestorDocument",
    "Project",
    "ProjectReturn",
    "Subscription",
    "SubscriptionConversion",
    "SubscriptionRequest",
    "User",
]


# 🔴 THE PER-FIRM SCOPE IS INSTALLED HERE, once, when the models are known. This is
# the only place where the four root tables are certain to exist, and it happens before
# any query at all goes out.
#
# ⚠️ INSTALLING IT LATER -- per session, per request -- would leave the FIRST query of a
# session unfiltered, and that is the query that fills a screen.
from app.core.firm_scope import install as _install_firm_scope  # noqa: E402

_install_firm_scope((Fund, Investor, Project, BankMovement))

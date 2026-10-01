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
from app.models.audit_log import AuditLog
from app.models.user import RevokedSession, User

__all__ = [
    "AuditLog",
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
    "RevokedSession",
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

# The audit journal listens to the unit of work from the same moment, and for the same
# reason: the first write of a session is a write like the others.
from app.core.audit import install as _install_audit  # noqa: E402

_install_audit()

"""Le Comptoir Invest — API."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import i18n

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ⚠️ NO MIGRATIONS AT STARTUP, and that is a decision taken against the sister product's
    # experience. Immo runs `upgrade head` in its lifespan and swallows the failure, so a
    # broken chain is invisible twice: no test replays it, and no alert follows it. Here the
    # schema is applied by the deployment, which fails loudly when it cannot.
    if not settings.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is not set: it derives the key that encrypts investors' bank "
            "details. Refusing to start rather than write them in clear."
        )

    # The first account, and only when nobody can administer yet. A failure here must not
    # stop the API: a fund that cannot be signed into is bad, a fund that will not start is
    # worse, and the reason is logged either way.
    if settings.BOOTSTRAP_MANAGER_EMAIL:
        if not settings.BOOTSTRAP_MANAGER_PASSWORD:
            logger.warning(
                "BOOTSTRAP_MANAGER_EMAIL is set without BOOTSTRAP_MANAGER_PASSWORD: "
                "no bootstrap account. A generated password would have to be logged to be "
                "of any use, and a credential in a log has stopped being a secret."
            )
        else:
            from app.database import AsyncSessionLocal
            from app.startup.bootstrap import ensure_first_manager

            try:
                async with AsyncSessionLocal() as db:
                    await ensure_first_manager(
                        db,
                        email=settings.BOOTSTRAP_MANAGER_EMAIL,
                        password=settings.BOOTSTRAP_MANAGER_PASSWORD,
                    )
            except Exception:  # noqa: BLE001
                logger.exception("The first manager could not be bootstrapped")

    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)


@app.middleware("http")
async def carry_the_readers_language(request, call_next):
    """Set the request's language before anything can produce a message.

    🔴 A MIDDLEWARE RATHER THAN A DEPENDENCY, because the refusals are built deep in pure
    functions that no dependency reaches: `accrual`, `eligibility`, `performance` have no
    request. The ContextVar is ambient by design, and this is the one place that fills it.

    ⚠️ IT MUST RUN BEFORE THE ROUTE, not after: a message rendered while the variable still
    holds the previous request's language is exactly the bug a per-process cache would have
    caused, one request later.
    """
    i18n.set_current_lang(
        i18n.lang_from_accept_language(request.headers.get("accept-language"))
    )
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "app": settings.APP_NAME}


from app.api.v1.auth import router as auth_router  # noqa: E402
from app.api.v1.billing import router as billing_router  # noqa: E402
from app.api.v1.internal_admin import router as internal_router  # noqa: E402
from app.api.v1.distributions import router as distributions_router  # noqa: E402
from app.api.v1.funds import router as funds_router  # noqa: E402
from app.api.v1.investors import router as investors_router  # noqa: E402
from app.api.v1.performance import router as performance_router  # noqa: E402
from app.api.v1.projects import router as projects_router  # noqa: E402
from app.api.v1.statements import router as statements_router  # noqa: E402
from app.api.v1.subscriptions import router as subscriptions_router  # noqa: E402
from app.api.v1.treasury import router as treasury_router  # noqa: E402

app.include_router(auth_router, prefix="/api/v1")
app.include_router(investors_router, prefix="/api/v1")
app.include_router(subscriptions_router, prefix="/api/v1")
app.include_router(treasury_router, prefix="/api/v1")
app.include_router(funds_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(distributions_router, prefix="/api/v1")
app.include_router(statements_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")
app.include_router(performance_router, prefix="/api/v1")

# 🔴 MOUNTED AT THE ROOT, WITHOUT `/api`. The edge proxy forwards only `/api/` and
# `/health` to this backend; everything else goes to the front end, whose SPA fallback
# answers `index.html`.
# `https://invest.lecomptoir.services/internal/managers` atteint donc une page statique et
# never this router: it is reachable only from the Docker network, where Alice lives.
# Moving it under `/api` would publish the fund's account administration on the open
# internet, behind a single shared header. The prefix is not cosmetic.
app.include_router(internal_router)

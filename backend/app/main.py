"""Le Comptoir Invest — API."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
                "BOOTSTRAP_MANAGER_EMAIL est defini sans BOOTSTRAP_MANAGER_PASSWORD : "
                "aucun compte d'amorcage. Un mot de passe genere devrait etre journalise "
                "pour servir, et un identifiant dans un journal n'est plus un secret."
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
                logger.exception("Amorcage du premier gestionnaire impossible")

    yield


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

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
from app.api.v1.investors import router as investors_router  # noqa: E402
from app.api.v1.projects import router as projects_router  # noqa: E402
from app.api.v1.statements import router as statements_router  # noqa: E402
from app.api.v1.subscriptions import router as subscriptions_router  # noqa: E402
from app.api.v1.treasury import router as treasury_router  # noqa: E402

app.include_router(auth_router, prefix="/api/v1")
app.include_router(investors_router, prefix="/api/v1")
app.include_router(subscriptions_router, prefix="/api/v1")
app.include_router(treasury_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(distributions_router, prefix="/api/v1")
app.include_router(statements_router, prefix="/api/v1")
app.include_router(billing_router, prefix="/api/v1")

# 🔴 MONTÉ À LA RACINE, SANS `/api`. Le proxy edge ne transmet que `/api/` et `/health` à
# ce backend ; tout le reste part vers le front, dont le repli SPA répond `index.html`.
# `https://invest.lecomptoir.services/internal/managers` atteint donc une page statique et
# jamais ce routeur : il n'est joignable que depuis le réseau Docker, où vit Alice.
# Le déplacer sous `/api` publierait l'administration des comptes du fonds sur Internet,
# derrière un simple en-tête partagé. Le préfixe n'est pas cosmétique.
app.include_router(internal_router)

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

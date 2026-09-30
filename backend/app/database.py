"""Engine and session. Async everywhere, as the sister products are."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    """One session per request, committed on success and rolled back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


#: 🔴 THE ONE WAY A ROUTE TAKES ITS SESSION, and its scope is the point: « function » makes
#: FastAPI run the code after the `yield` above (the commit) BEFORE the answer leaves. With
#: the default scope of a dependency with `yield` (« request »), that code runs once the
#: response is SENT: a screen that saved and read back at once was answered from before the
#: save (customer recipe, 30 Sept 2026: 13 reads out of 15 missed the fund just created),
#: and a commit failing after a 201 was a success the database never kept. One alias for
#: every route, so one scope: it is part of FastAPI's cache key, and two would open two
#: sessions in one request. Guard: `tests_unit/test_a_saved_answer_is_committed_before_it_leaves.py`.
SESSION = Depends(get_db, scope="function")

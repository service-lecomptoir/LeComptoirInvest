"""Application settings.

⚠️ NO DEFAULT FOR `SECRET_KEY`. It derives the key that encrypts investors' bank details,
so a fallback value would mean every deployment that forgot to set one shares the same
encryption key — which is the same as having none, while looking encrypted.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Le Comptoir Invest"
    DEBUG: bool = False
    ENV: str = "development"

    #: Async URL (asyncpg). Alembic derives its own sync URL from this one.
    DATABASE_URL: str = "postgresql+asyncpg://invest_user:devpassword123@localhost:5432/lecomptoirinvest"

    #: Signs tokens AND derives the encryption key of the bank details. Required.
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    #: The fund's own accounts, one per currency it holds. Statement imports check that the
    #: file they were handed belongs to one of them: importing another entity's statement
    #: into this fund is the kind of mistake that is only found at reconciliation.
    FUND_IBANS: str = ""

    #: Alice, the SaaS console that owns manager accounts. Same contract as the sister
    #: products: a manager is never minted here.
    ALICE_URL: str = ""
    ALICE_INTERNAL_KEY: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in {"production", "prod"}

    @property
    def fund_ibans(self) -> list[str]:
        return [
            x.strip().upper() for x in (self.FUND_IBANS or "").split(",") if x.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    return Settings()

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

    #: 🔴 DEUX CLÉS, DEUX SENS, ET ELLES NE SONT PAS INTERCHANGEABLES.
    #:
    #: `ALICE_INTERNAL_KEY` est la clé ENTRANTE : celle qu'Alice présente en appelant
    #: `/internal`, et que ce produit vérifie. `ALICE_API_KEY` est la clé SORTANTE : celle
    #: que ce produit présente en interrogeant Alice sur son propre abonnement.
    #:
    #: Les confondre sous un seul nom ne casse rien de visible : les appels sortants sont
    #: simplement refusés en 401, l'écran d'abonnement se dégrade en « non piloté », et on
    #: en conclut qu'aucune console ne gère l'instance. Pire, réutiliser la clé entrante
    #: pour sortir reviendrait à faire circuler le secret qui protège l'administration des
    #: comptes du fonds dans des appels qui n'en ont pas besoin.
    ALICE_INTERNAL_KEY: str = ""
    ALICE_API_KEY: str = ""

    #: The first fund-wide account, created ONLY when nobody can administer the fund yet.
    #: See `app/startup/bootstrap.py`: it is an escape hatch until Alice drives this
    #: product, and it is inert the moment anybody can sign in as a manager.
    #: ⚠️ No default password: a generated one would have to be logged to be usable, and a
    #: credential in a log is a credential everybody with log access holds.
    BOOTSTRAP_MANAGER_EMAIL: str = ""
    BOOTSTRAP_MANAGER_PASSWORD: str = ""

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

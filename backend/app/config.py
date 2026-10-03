"""Application settings.

⚠️ NO DEFAULT FOR `SECRET_KEY`. It signs the session tokens and, until the data key is made
explicit in `DATA_ENCRYPTION_KEYS`, derives the key that encrypts investors' bank details:
a fallback value would mean every deployment that forgot to set one shares the same
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

    #: Signs the session tokens. Required. While `DATA_ENCRYPTION_KEYS` is empty it ALSO
    #: derives the key of the bank details, exactly as it always did.
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 720

    #: 🔴 THE KEYS OF THE BANK DETAILS, APART FROM THE SESSION SECRET. Comma-separated
    #: Fernet keys: the FIRST encrypts, EVERY one is tried to decrypt (`core/crypto.py`).
    #: Empty: the one key derived from `SECRET_KEY`, byte for byte as before, so an
    #: installation that never set it reads its data unchanged. Once set, rotating
    #: `SECRET_KEY` no longer touches the data. Rotated with `docs/rotation_cle_donnees.ps1`
    #: and `python -m app.services.reencrypt`, never edited by hand without that pass.
    DATA_ENCRYPTION_KEYS: str = ""

    #: The fund's own accounts, one per currency it holds. Statement imports check that the
    #: file they were handed belongs to one of them: importing another entity's statement
    #: into this fund is the kind of mistake that is only found at reconciliation.
    FUND_IBANS: str = ""

    # ── Sending a notice to an investor ────────────────────────────────────────────────
    #: 🔴 THE CONNECTION IS SHARED ACROSS THE PLATFORM, THE IDENTITY NEVER IS. One relay, one
    #: credential, rotated in one place; but `SMTP_FROM_EMAIL` has NO DEFAULT. An
    #: installation that forgets it cannot send, which is the right failure. A fallback on a
    #: sibling's address would put « Le Comptoir Immo » on this fund's capital call, and the
    #: investor would be right to read that as a phishing attempt.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    #: This product's own name. A default is safe here because it names ITSELF.
    SMTP_FROM_NAME: str = "Le Comptoir Invest"
    SMTP_TLS: bool = True

    #: How many days a line of the audit journal is kept, as in every sibling product
    #: (the manager, 27 Sept 2026). Purged once a day by `services/audit_retention.py`;
    #: `0` keeps everything. Only the journal: never the business data.
    AUDIT_RETENTION_DAYS: int = 90

    #: Where this product's screens are served: the links a letter carries (choosing a
    #: password) point there. A default is safe here because it names ITSELF, as
    #: `SMTP_FROM_NAME` does; a local run sets its own.
    PUBLIC_APP_URL: str = "https://invest.lecomptoir-services.com"

    #: Alice, the SaaS console that owns manager accounts. Same contract as the sister
    #: products: a manager is never minted here.
    ALICE_URL: str = ""

    #: 🔴 TWO KEYS, TWO DIRECTIONS, AND THEY ARE NOT INTERCHANGEABLE.
    #:
    #: `ALICE_INTERNAL_KEY` is the INBOUND key: the one Alice presents when calling
    #: `/internal`, and that this product verifies. `ALICE_API_KEY` is the OUTBOUND key:
    #: the one this product presents when asking Alice about its own subscription.
    #:
    #: Merging them under one name breaks nothing visible: outbound calls are simply
    #: refused with a 401, the subscription screen degrades to « not managed », and one
    #: concludes no console drives the instance. Worse, reusing the inbound key for
    #: outbound calls would circulate the secret that protects the fund's account
    #: administration through calls that have no need of it.
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

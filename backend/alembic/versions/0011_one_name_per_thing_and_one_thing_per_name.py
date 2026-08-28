"""Un nom par chose, et une chose par nom

Deux colonnes s appelaient `national_id`, et elles ne designaient pas la meme chose.

🔴 `users.national_id` EST LE NUMERO D IMMATRICULATION DE LA SOCIETE DE GESTION, celui qui
figure sur ses factures. C est la notion que la plateforme nomme `company_number` -- SIRET
en France, RCCM en Cote d Ivoire, ICE au Maroc. Renommee, sans autre changement.

🔴 `investors.national_id` TENAIT DEUX NOTIONS DANS UNE COLONNE, et son propre commentaire
l avouait : « SIREN, company number, national identity number -- whatever their country
issues ». Or `investors.kind` dit deja laquelle :

  - une PERSONNE MORALE a un numero d entreprise -> `company_number` ;
  - une PERSONNE PHYSIQUE a un numero de PIECE D IDENTITE, exige par les obligations de
    connaissance du client -> `identity_document_number`.

Ce ne sont pas deux orthographes d une meme chose : ce sont deux choses. Les melanger
empeche de verifier l une comme l autre, puisqu on ne sait pas laquelle on lit.

⚠️ ET LE TYPE DE PIECE ARRIVE AVEC LE NUMERO. « 12AB34567 » ne se verifie pas si on ignore
s il faut le lire comme un passeport ou une carte nationale. Ajoute maintenant plutot que
plus tard : apres coup, personne ne saurait dire de quelle piece venaient les numeros deja
saisis, et il faudrait rouvrir chaque fiche.

⚠️ LA REPARTITION SUIT `kind`, ET LES LIGNES SANS `kind` CONNU RESTENT OU ELLES SONT. Une
valeur deplacee dans la mauvaise colonne serait pire que non deplacee : elle affirmerait
une nature de document que personne n a verifiee.

Revision ID: 0011_one_name_per_thing_and_one_thing_per_name
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0011_one_name_per_thing_and_one_thing_per_name"
down_revision: str | None = "0010_firm_isolation"
branch_labels = None
depends_on = None


def _has_column(table: str, name: str) -> bool:
    """⚠️ DIT DANS QUEL SCHEMA ELLE REGARDE. `information_schema` couvre tous les schemas
    visibles ; une sonde muette repond sur `public` pendant que `op.*` travaille ailleurs,
    et le travail est saute EN SILENCE -- ce qui ressemble a une reussite."""
    return bool(
        op.get_bind().scalar(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": name},
        )
    )


def upgrade() -> None:
    bind = op.get_bind()

    # 1. La societe de gestion : un simple renommage.
    if _has_column("users", "national_id") and not _has_column("users", "company_number"):
        op.alter_column("users", "national_id", new_column_name="company_number")

    # 2. L investisseur : une colonne devient trois.
    if not _has_column("investors", "company_number"):
        op.add_column("investors", sa.Column("company_number", sa.String(length=60), nullable=True))
    if not _has_column("investors", "identity_document_number"):
        op.add_column(
            "investors",
            sa.Column("identity_document_number", sa.String(length=60), nullable=True),
        )
    if not _has_column("investors", "identity_document_type"):
        op.add_column(
            "investors", sa.Column("identity_document_type", sa.String(length=30), nullable=True)
        )

    if _has_column("investors", "national_id"):
        # ⚠️ CHACUN DANS SA COLONNE, SELON `kind`. Le type de piece n est PAS devine : on
        # ne connait pas la nature d un document qu on n a jamais demandee, et l inventer
        # serait affirmer une verification qui n a pas eu lieu.
        bind.execute(
            sa.text(
                "UPDATE investors SET company_number = national_id "
                "WHERE kind = 'societe' AND national_id IS NOT NULL"
            )
        )
        bind.execute(
            sa.text(
                "UPDATE investors SET identity_document_number = national_id "
                "WHERE kind = 'personne' AND national_id IS NOT NULL"
            )
        )
        # 🔴 ET LA COLONNE NE PART QUE SI PLUS RIEN N Y RESTE. La premiere version de
        # cette migration COMPTAIT les lignes au `kind` inconnu, l annoncait, puis
        # supprimait la colonne quand meme -- donc leur valeur avec. Une migration qui
        # signale ce qu elle detruit ne le detruit pas moins.
        #
        # ⚠️ ELLE S ARRETE PLUTOT QUE DE PERDRE. `kind` ne devrait valoir que « societe »
        # ou « personne » ; « devrait » n est pas « vaut ». S il reste une ligne, personne
        # ne peut deviner dans laquelle des deux colonnes elle va -- et l inventer
        # affirmerait une nature de document que nul n a verifiee.
        orphelins = bind.scalar(
            sa.text(
                "SELECT count(*) FROM investors "
                "WHERE national_id IS NOT NULL AND kind NOT IN ('societe', 'personne')"
            )
        )
        if orphelins:
            raise RuntimeError(
                f"{orphelins} investisseur(s) portent un numero et un `kind` qui n est ni "
                "« societe » ni « personne ». Leur valeur n a pas de colonne d arrivee : "
                "corrigez leur `kind`, puis rejouez. La colonne `national_id` est laissee "
                "en place -- rien n est perdu."
            )
        op.drop_column("investors", "national_id")


def downgrade() -> None:
    if not _has_column("investors", "national_id"):
        op.add_column("investors", sa.Column("national_id", sa.String(length=60), nullable=True))
        op.get_bind().execute(
            sa.text(
                "UPDATE investors SET national_id = "
                "COALESCE(company_number, identity_document_number)"
            )
        )
    for name in ("company_number", "identity_document_number", "identity_document_type"):
        if _has_column("investors", name):
            op.drop_column("investors", name)
    if _has_column("users", "company_number") and not _has_column("users", "national_id"):
        op.alter_column("users", "company_number", new_column_name="national_id")

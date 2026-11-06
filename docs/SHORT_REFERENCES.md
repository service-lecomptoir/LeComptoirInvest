# Les références courtes dans Le Comptoir Invest

Décision du propriétaire (6 nov. 2026) : **une adresse de fiche ne montre jamais un
identifiant technique** (`/leases/0ad7e24e-…` devient `/leases/B-0042`). La règle, le
catalogue des lettres et le motif commun sont dans `docs/SHORT_REFERENCES.md` de
**Le Comptoir Alice**.

Invest n'a aujourd'hui **aucune fiche à adresse** : ses écrans sont plats (fonds, projets,
investisseurs, appels… sont des listes). Le seul paramètre de route est le jeton du lien
« choisir mon mot de passe » (`/set-password/:token`), qui est un secret, pas une fiche.

La garde `frontend/src/lib/recordAddresses.test.ts` refuse dès maintenant toute route à
paramètre. La première fiche d'Invest qui aura son écran :

1. prend ses lettres dans le catalogue d'Alice (et les y écrit) ;
2. recopie le cœur commun `backend/app/core/short_reference.py` (empreinte vérifiée) et
   suit le motif d'Immo : colonnes `short_reference` et `short_reference_scope_id`
   numérotées par cabinet (`firm_id`), migration qui numérote l'existant puis déclencheur,
   `GET /short-references/{référence}`, écran lu par `useRecordParam`, liens par
   `recordPath`, référence affichée en tête de fiche et trouvée par la recherche ;
3. ajoute sa route à la garde.

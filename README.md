# Le Comptoir Invest

Un fonds d'investissement : des investisseurs y placent de l'argent, le fonds le déploie
dans des projets, les projets rapportent, les investisseurs sont payés. L'outil n'a qu'un
vrai travail — que ces quatre mouvements se recoupent **toujours**.

> État au 18 août 2026 : **le backend complet.** Treize tables, deux migrations, 15 routes,
> 56 gardes vertes. Les quatre mouvements d'argent existent et l'invariant de trésorerie est
> vérifié de bout en bout. Pas encore d'écran.

---

## Les décisions prises, avec leur date

| Décision | Valeur | Pourquoi elle est écrite ici |
|---|---|---|
| Nom | **Le Comptoir Invest** | entre dans le registre d'Alice, les URL et les e-mails : se change mal |
| Nature | **fonds d'abord** ; le prêt est un pont | les instruments ne sont pas symétriques |
| Ordre de remboursement | **le prêt passe avant** | l'ordre usuel, et le seul qui tienne en liquidation |
| Conversion | **prêt → souscription**, jamais l'inverse | voir `instruments.may_convert` |
| Devises | **multi-devises dès la première ligne** | Immo a payé cher son euro codé en dur |
| KYC | **un verdict qui bloque l'argent** | un contrôle qui ne bloque rien est du théâtre |

---

## Les quatre montants qu'il ne faut jamais confondre

| Montant | Ce que c'est |
|---|---|
| **Engagement** | ce que l'investisseur a promis |
| **Appel de fonds** | ce qu'on lui demande, à une date |
| **Versement** | ce qui est arrivé sur le compte, rapproché du relevé |
| **Distribution** | ce qu'on lui reverse, **scindé capital / revenu** |

Afficher les engagements comme de la trésorerie fait appeler des fonds déjà dépensés. Une
distribution non scindée produit un relevé fiscal faux. **Ces deux erreurs ne se voient
pas : les totaux tombent juste.**

---

## L'invariant

```
trésorerie(devise) = Σ versements(devise)
                   − Σ déploiements(devise)
                   + Σ retours(devise)
                   − Σ distributions(devise)
```

**Une équation par devise, jamais une somme entre elles.** Un total mêlant euros et francs
CFA n'est pas une trésorerie : c'est un nombre qui n'est un solde nulle part, et il aura
l'air juste puisqu'il additionne des montants réels.

---

## Ce qui existe

| Fichier | Ce qu'il tient |
|---|---|
| `app/core/instruments.py` | les deux instruments, **les deux ordres** (liquidation imposée / distribution contractuelle), la conversion à sens unique |
| `app/core/kyc.py` | les quatre états, le verdict qui **bloque l'argent**, la péremption d'une acceptation |
| `app/core/money.py` | `Money` indissociable de sa devise, l'arithmétique qui **refuse** de mélanger, les décimales réelles par devise |
| `app/core/crypto.py` | chiffrement des IBAN, et l'**empreinte salée** qui permet de rapprocher sans déchiffrer |
| `app/core/references.py` | la référence que l'investisseur recopie : alphabet sans ambiguïté, **caractère de contrôle**, extraction d'un libellé bancaire, QR EPC |
| `app/core/matching.py` | **à qui appartient ce virement** : les quatre indices par ordre de ce qu'ils prouvent, et le refus de deviner |
| `app/models/` | 10 tables : investisseurs, pièces, comptes, souscriptions, demandes, conversions, mouvements, appels, contributions, distributions |
| `app/services/` | rapprochement, portefeuille dérivé, résultat par projet |
| `app/api/v1/` | 15 routes : connexion, registre, KYC, demandes, conversion, trésorerie, portefeuille |
| `alembic/versions/` | **0001** le socle, **0002** les projets. La chaîne va jusqu'à head contre une base vide |
| `tests_unit/` + `tests/` | 56 gardes, dont la **base de test bâtie par les migrations** |

## Le rapprochement, par ordre de ce que chaque indice prouve

| Indice | Ce qu'il identifie | Force |
|---|---|---|
| **le compte d'arrivée** (IBAN virtuel) | l'investisseur, sans interprétation | le seul sans ambiguïté |
| **la référence** dans le libellé | l'appel, donc la souscription et l'investisseur | forte, mais elle passe par un humain qui recopie |
| **le compte émetteur** | l'investisseur, **jamais** l'appel | un prêteur paie ses quatre appels du même compte |
| **le montant** | rien | deux investisseurs appelés à 50 000 EUR la même semaine, ce n'est pas une coïncidence |

⚠️ Le nom du donneur d'ordre **n'est pas un indice, c'est un contrôle** : un nom qui ne
correspond pas est un **paiement de tiers**, un constat en soi.

🔴 **La règle propose, elle ne décide jamais.** Un humain impute, et `attributed_by`
enregistre qui. Imputer automatiquement un virement de 200 000 EUR sur un nom qui
ressemblait n'est pas un gain de temps.

## Ce qui n'existe pas encore

Les écrans, l'enregistrement dans Alice, le déploiement. Et le **relevé fiscal** de chaque
investisseur, qui découle des distributions déjà scindées capital / revenu.

---

## Démarrer

**🔴 Ce produit a SA PROPRE base.** Ni un schéma dans celle d'un autre, ni une base
partagée : le registre des investisseurs et les mouvements bancaires du fonds ne partagent
ni sauvegarde, ni restauration, ni export avec un outil de gestion locative. À créer une
fois, avec un rôle qui en a le droit :

```sql
CREATE ROLE invest_user LOGIN PASSWORD '...';
CREATE DATABASE lecomptoirinvest OWNER invest_user;
```

```
cd backend && pip install -r requirements.txt
export SECRET_KEY=...            # obligatoire : il dérive la clé de chiffrement des IBAN
export DATABASE_URL=postgresql+asyncpg://invest_user:...@localhost:5432/lecomptoirinvest
python -m alembic upgrade head
python -m pytest -q
```

La suite **refuse de démarrer** si cette base est absente, plutôt que de se rabattre sur
une autre : une exécution qui décrit silencieusement le mauvais endroit est pire qu'une
exécution qui n'a pas lieu. `INVEST_TEST_DB` permet de passer outre, sciemment.

⚠️ `SECRET_KEY` n'a **aucune valeur par défaut**. Un repli donnerait à tout déploiement qui
l'oublie la même clé de chiffrement, c'est-à-dire aucun chiffrement avec l'apparence du
contraire.

## ⚠️ Le cadre réglementaire décide de colonnes, pas seulement de droit

Identification des investisseurs et origine des fonds, version du document d'information
reçue par chacun, bulletin de souscription horodaté, preuve d'envoi des relevés. Ce sont des
champs et des dates. Ajoutés après coup sur un historique déjà constitué, ils ne se
remplissent jamais complètement.

La forme juridique du véhicule se décide avec un conseil ; elle change ce que l'outil doit
enregistrer, et c'est à ce titre qu'elle est un sujet d'ingénierie ici.

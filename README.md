# Le Comptoir Invest

Un fonds d'investissement : des investisseurs y placent de l'argent, le fonds le déploie
dans des projets, les projets rapportent, les investisseurs sont payés. L'outil n'a qu'un
vrai travail — que ces quatre mouvements se recoupent **toujours**.

> État au 18 août 2026 : **en production sur https://invest.lecomptoir.services.**
> Les quatre mouvements existent de bout en bout, l'invariant de trésorerie est vérifié,
> la cascade de distribution est appliquée et gardée. Le contrat `/internal` existe et
> Alice pilote le produit. Toutes les gardes sont exigées par le pipeline **avant** que
> l'image soit construite.
>
> État au 19 août 2026 : **le véhicule est une entité**, et le périmètre par véhicule est
> atteignable depuis les écrans ; **les refus du serveur sont bilingues**.

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
| Encaissement | **virement seul** | l'analyse est gardée en tête de `treasury_service.py` |
| Nomenclature | **tout en anglais** : code, valeurs stockées, URL | 18 valeurs françaises corrigées le 18 août, avant qu'il y ait des lignes |

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

## 🔴 La cascade, et ce qui la rend utile

Servir les prêteurs d'abord ne décide que du partage de ce qui **est** distribué. Un fonds
peut honorer cet ordre parfaitement et faire défaut le même après-midi. Ce qui protège
réellement le prêteur, c'est la **deuxième** règle :

1. les prêteurs sont servis d'abord, **au prorata entre eux** quand la somme ne suffit pas ;
2. **rien ne va aux souscripteurs tant que la dette n'est pas couverte.**

Et un prêt dont le montant dû n'est pas calculable **bloque tout** : sans réponse à
« les prêteurs sont-ils couverts », personne ne peut être présenté comme payable.

---

## Ce qui existe

### Serveur

| Fichier | Ce qu'il tient |
|---|---|
| `app/core/instruments.py` | les deux instruments, **les deux ordres** (liquidation imposée / distribution contractuelle), la conversion à sens unique |
| `app/core/accrual.py` | **ce qu'un prêteur est dû**, en jours, sur une convention nommée ; ce qui n'est pas calculable est refusé avec un motif ; une répartition qui ne perd pas un centime |
| `app/core/kyc.py` | les quatre états, le verdict qui **bloque l'argent**, la péremption d'une acceptation |
| `app/core/money.py` | `Money` indissociable de sa devise, l'arithmétique qui **refuse** de mélanger |
| `app/core/crypto.py` | chiffrement des IBAN, et l'**empreinte salée** qui permet de rapprocher sans déchiffrer |
| `app/core/references.py` | la référence que l'investisseur recopie : alphabet sans ambiguïté, caractère de contrôle, QR EPC |
| `app/core/matching.py` | **à qui appartient ce virement** : quatre indices par ordre de ce qu'ils prouvent, et le refus de deviner |
| `app/services/distribution_service.py` | **la cascade et sa garde**, portée par véhicule |
| `app/models/fund.py` + `app/api/v1/funds.py` | **le véhicule** : ce qui regroupe projets et souscripteurs, et dont ils partagent les conditions ; l'actif net, qui **refuse** de se totaliser quand deux fonds partagent un compte |
| `app/core/i18n.py` | **la langue du lecteur**, décidée par requête et jamais par processus ; `pick(fr, en)` au site d'appel, jamais un catalogue ailleurs |
| `app/services/statement_service.py` | le relevé fiscal : l'année du **paiement**, jamais de la décision |
| `app/api/v1/` | 25 routes : connexion, registre, KYC, demandes, conversion, trésorerie, appels, projets, distributions, relevés |
| `alembic/versions/` | **0001** le socle, **0002** les projets. La chaîne va jusqu'à head contre une base vide |
| `tests/` + `tests_unit/` | **99 gardes**, dont la base de test bâtie par les migrations |

### Interface

Vite + React + TypeScript + Tailwind, aux codes des consoles de fonds du marché : bandeau
de KPI, tables denses à chiffres alignés en chasse tabulaire, pastilles d'état sobres,
barre latérale navy. **Deux navigations distinctes** — celle du gestionnaire et celle de
l'investisseur — et non une seule avec des lignes grisées.

| Écran | Ce qu'il montre |
|---|---|
| `Dashboard` | la trésorerie **et la dette qu'elle porte déjà**, par devise |
| `Treasury` | import de relevé, argent non identifié, imputation, appels de fonds |
| `Projects` | déployé, capital rendu, produit, multiple |
| `Distributions` | **la cascade, dessinée comme une cascade**, et le refus en toutes lettres |
| `Investors` | le registre et les verdicts ; l'IBAN n'est **pas** dans la liste |
| `Subscriptions` | accepter ou refuser une demande, motif obligatoire |
| `Funds` | les véhicules, leurs conditions, leur compte, et **l'actif net du véhicule choisi** |
| `Portfolio` `Calls` `MyDistributions` `Statement` | l'espace de l'investisseur |

**Français et anglais**, sélecteur à drapeaux SVG, clé de stockage partagée avec les
produits frères (`lecomptoir-lang`). Le catalogue anglais est **écrit à la main** et
`npm run i18n:check` refuse une entrée anglaise identique à sa version française.

🔴 **Et les phrases du serveur se traduisent au serveur.** Ce produit refuse pour des motifs
qui sont sa raison d'être — les prêteurs ne sont pas couverts, ce prêt n'a pas d'échéancier
enregistré, ce virement est une entrée — et l'interface affiche `detail` tel quel. Le client
envoie donc `Accept-Language` depuis le choix fait dans le sélecteur, et non celui du système
d'exploitation. Deux gardes le tiennent : l'une exige que **toute** phrase posée dans un
emplacement lu par un humain passe par `pick(fr, en)` sans regarder la langue, l'autre
cherche du français resté dehors. La première existe parce que la seconde ne peut pas
suffire : « Statut inconnu » ne porte ni accent ni article, et a traversé trois balayages.

## Déploiement

`git push` sur `main` suffit : le pipeline lance **les gardes d'abord** (ruff + 99 tests
serveur, puis `i18n:check` + `tsc` + vitest), construit les deux images, les pousse sur
ghcr.io, et le VPS les tire. Les produits frères déploient sans passer leurs tests ; ici la
valeur du produit **est** l'arithmétique, et une erreur y est invisible.

| Élément | Valeur |
|---|---|
| Domaine | `invest.lecomptoir.services`, certificat dédié |
| Projet compose | **`invest`** — jamais `docker` : le préfixe nomme les volumes, et un mauvais projet monte un volume **vide** |
| Conteneurs | `invest_backend` (8001), `invest_frontend` (80), `invest_db` |
| Réseau | `lecomptoir_net` (partagé), proxy `edge_nginx` |
| Secrets | `~/LeComptoirInvest/backend/.env.prod` sur le VPS, **hors dépôt** |

Les migrations tournent dans le `CMD` de l'image, **avant** uvicorn : un échec arrête le
conteneur, qui boucle à la vue de tous plutôt que de servir un ancien schéma.

## Ce qui n'existe pas encore

Un envoi de texte hors requête — relevé en PDF, e-mail de relance — n'existe pas encore.
`i18n.use_lang()` est le mécanisme prévu pour lui : il force la langue du **destinataire**,
qui n'est pas celle du gestionnaire qui déclenche l'envoi. Il n'a aucun appelant en
production aujourd'hui, et c'est écrit ici plutôt que laissé à découvrir.

`app/startup/bootstrap.py` crée le premier gestionnaire — et **seulement** si personne ne
peut administrer le fonds.

---

## Démarrer

**🔴 Ce produit a SA PROPRE base.** Ni un schéma dans celle d'un autre, ni une base
partagée : le registre des investisseurs et les mouvements bancaires du fonds ne partagent
ni sauvegarde, ni restauration, ni export avec un outil de gestion locative.

```sql
CREATE ROLE invest_user LOGIN PASSWORD '...';
CREATE DATABASE lecomptoirinvest OWNER invest_user;
```

```
cd backend && pip install -r requirements-dev.txt   # runtime + pytest + ruff
cp .env.example .env        # puis renseigner SECRET_KEY et DATABASE_URL
python -m alembic upgrade head
python -m pytest -q

cd ../frontend && npm install && npm run dev
```

L'API écoute sur **8001**, l'interface sur **5175** — et ces numéros ne sont pas libres :
Le Comptoir Immo occupe déjà 8000, 5173, 5174 et 5180. Deux applications qui se disputent
un port, c'est un écran qui sert les données d'un autre produit à quelqu'un qui fait
confiance à la barre d'adresse.

La suite **refuse de démarrer** si la base dédiée est absente, plutôt que de se rabattre
sur une autre. `INVEST_TEST_DB` permet de passer outre, sciemment.

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

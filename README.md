# Le Comptoir Invest

Un fonds d'investissement : des investisseurs y placent de l'argent, le fonds le déploie
dans des projets, les projets rapportent, les investisseurs sont payés. L'outil n'a qu'un
vrai travail — que ces quatre mouvements se recoupent **toujours**.

> État au 17 août 2026 : **le noyau du domaine, rien d'autre.** Pas encore de base, pas
> d'API, pas d'écran. Ce qui est écrit ici est ce qui devait l'être en premier, parce qu'un
> modèle de domaine faux coûte bien plus cher qu'un écran raté.

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

## Ce qui n'existe pas encore

Les modèles persistés, la base, les migrations, l'API, les écrans, l'enregistrement dans
Alice, le déploiement. Dans l'ordre fixé : **registre des investisseurs → suivi de l'argent
→ projets et allocation → reporting investisseur**.

---

## ⚠️ Le cadre réglementaire décide de colonnes, pas seulement de droit

Identification des investisseurs et origine des fonds, version du document d'information
reçue par chacun, bulletin de souscription horodaté, preuve d'envoi des relevés. Ce sont des
champs et des dates. Ajoutés après coup sur un historique déjà constitué, ils ne se
remplissent jamais complètement.

La forme juridique du véhicule se décide avec un conseil ; elle change ce que l'outil doit
enregistrer, et c'est à ce titre qu'elle est un sujet d'ingénierie ici.

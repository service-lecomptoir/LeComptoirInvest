# La double authentification (2FA) dans Le Comptoir Invest

Décision du propriétaire (2 nov. 2026) : un code TOTP à 6 chiffres (RFC 6238), lu dans une
application d'authentification. **Proposée à tous les comptes**, **recommandée** par un
bandeau discret à qui gère le fonds : le gestionnaire (`manager`, l'abonné et les collègues
de sa société de gestion) et l'administrateur de la plateforme (`admin`). Un compte
investisseur peut l'activer dans son profil ; il n'est pas invité par le bandeau. Jamais
obligatoire dans le produit.

Le motif commun est décrit dans `docs/TWO_FACTOR.md` de **Le Comptoir Alice** : le calcul vit
dans `backend/app/core/two_factor.py`, le même fichier dans chaque produit, son empreinte
SHA-256 vérifiée par `test_the_two_factor_core_is_the_shared_one`.

⚠️ Ce dépôt formate à 88 colonnes, le cœur est écrit à 100 : `backend/ruff.toml` l'exclut du
formatage (et de lui seul) pour qu'il reste octet pour octet celui d'Alice. Le linter le lit.

## Ce qu'Invest porte

- Table `user_two_factors` (une ligne par compte qui l'a préparée, migration `0016`) : la clé
  chiffrée par `app/core/crypto.py`, **le trousseau qui chiffre déjà les IBAN**
  (`DATA_ENCRYPTION_KEYS`) ; la colonne est parcourue par `services/reencrypt.py`, donc une
  rotation de la clé des données emporte aussi les seconds facteurs. Le moment de
  l'activation, le dernier pas de temps accepté (aucun code accepté deux fois, UPDATE
  conditionnel), les empreintes des 10 codes de secours (HMAC clé par `SECRET_KEY` :
  changer `SECRET_KEY` rend caducs les codes de secours déjà tirés ; la clé TOTP, elle,
  suit le trousseau, qui ne dépend plus de `SECRET_KEY` une fois écrit en clair dans
  `DATA_ENCRYPTION_KEYS`).
- La colle : `app/services/two_factor_service.py` (lignes du journal `two_factor.*`,
  l'e-mail à la personne quand son second facteur est retiré, dans sa langue et à
  l'apparence choisie par sa société de gestion).
- Les routes, `app/api/v1/two_factor.py` :
  - `POST /auth/login` : avec le facteur actif, aucun jeton mais `two_factor_required` et un
    jeton intermédiaire de 5 minutes (`type = two_factor_pending`) ;
  - `POST /auth/login/two-factor` : le jeton intermédiaire et un code (ou un code de secours) ;
  - `GET /auth/two-factor`, `POST /auth/two-factor/setup | activate | backup-codes | disable` :
    la section « Sécurité » de « Mon profil ».
- Le plafond (`core/visitor_window.py`, la fenêtre par visiteur des portes publiques) : 10
  par minute pour la deuxième étape, 5 pour les gestes de « Sécurité ». Depuis le 5 nov. 2026,
  10 par minute pour le mot de passe aussi (`auth._login_window` ; il n'en avait aucun) : au-delà,
  429 et une phrase dans la langue du lecteur.
- 🔴 La porte (`deps.current_user`) refuse tout jeton dont le `type` n'est pas `access` : le
  jeton intermédiaire n'ouvre rien d'autre. Elle refuse du même coup un lien de mot de passe
  présenté comme une session (`Authorization: Bearer`), ce qu'elle acceptait jusqu'au 3 nov.
  2026 (même clé, même `sub` ; mesuré : `/auth/me` répondait 200). Un jeton de session émis
  avant ce champ n'en porte pas et vit ses douze heures.
- Journal : `two_factor.enabled`, `.disabled`, `.failed`, `.backup_code_used`,
  `.backup_codes_regenerated`, `.reset` (entité `users`, jamais un code), écrits par
  `audit.record`. La table elle-même est hors du journal générique
  (`audit_rules.NEVER_AUDITED`), et ses colonnes y seraient masquées par leur nom.

## Qui retire la double authentification d'un autre

Aucun écran d'Invest n'administre un autre compte : la console d'Alice crée, bloque et
réinitialise les comptes des gestionnaires par `/internal`, et aucun écran du fonds n'ouvre,
ne bloque ni ne réinitialise le compte d'un collègue ou d'un investisseur. Il n'existe donc
pas de vérification de périmètre (société, fonds) à reprendre pour une route : le retrait
passe par le serveur, jamais par une route (une route qui retire le facteur serait la seule
porte qu'un mot de passe volé demande) :

```
docker exec -it invest_backend python -m scripts.reset_two_factor <adresse>
docker exec -it invest_backend python -m scripts.reset_two_factor <adresse> --yes
```

La commande nomme le compte et demande `YES` (sauf `--yes`), retire la clé, les codes de
secours et l'activation, écrit `two_factor.reset` (`by` : `script:<compte>@<machine>`) et
envoie un e-mail à la personne. Son propre second facteur se retire dans « Sécurité », mot de
passe ET code.

## Les connexions sans mot de passe

| Connexion | Traitement |
|---|---|
| Lien « Choisir mon mot de passe » (bienvenue d'un compte ouvert par la console, mot de passe oublié, lien demandé par la console) | Il ouvrait la session aussitôt. **Protégé : facteur actif, il fixe le mot de passe puis demande le code** (la page renvoie à l'étape « Code de vérification » de la connexion) ; un lien prouve la boîte mail, pas le téléphone. |
| Le même lien présenté comme jeton de session | Refusé (401) depuis le 3 nov. 2026 : la porte ne lit plus que les jetons `access`. |
| Lien de connexion de la console (`/internal/managers/{id}/login-link`) | **Protégé depuis le 5 nov. 2026** : l'administrateur de la console a passé SA double authentification, pas celle du titulaire. Facteur actif : aucune session, `{two_factor_required: true, two_factor_token, url: "/login#two_factor=<jeton>"}` (5 minutes, dans le fragment, que le navigateur n'envoie à aucun serveur) et la page de connexion ouvre l'étape « Code de vérification ». Sans facteur : `/login?token=<session>`, que la page de connexion lit enfin (elle l'ignorait : le lien n'ouvrait qu'un formulaire vide). |
| Mot de passe posé par la console (`/internal/managers/{id}/reset-password`) | Ce n'est pas une connexion sans mot de passe : la connexion suivante demande le code. |
| Espace investisseur ou associé par lien d'invitation | Il n'en existe pas : aucun écran ni aucune route ne crée un compte investisseur ni n'envoie d'invitation ; un compte investisseur se connecte par mot de passe (et son code s'il l'a activé). |
| SSO entre produits, jeton d'un autre produit, impersonation | Aucun : seule Alice parle à `/internal`, avec la clé. |

## Écrans

- Connexion : l'étape « Code de vérification », avec « Utiliser un code de secours » et
  « Revenir au mot de passe » ; la même étape après un lien de mot de passe.
- Mon profil › Sécurité : état, QR code et clé montrés une fois, un premier code, 10 codes
  de secours montrés une fois (Copier, Enregistrer (.txt), « J'ai mis ces codes en lieu
  sûr »), nouveaux codes et désactivation (mot de passe et code).
- Le bandeau « Protégez votre compte : activez la double authentification » pour qui gère
  le fonds sans second facteur ; « Plus tard » le tait 30 jours, compte par compte.

Tests : `backend/tests/test_an_account_may_ask_a_second_factor.py`,
`frontend/src/components/security/theSecondFactorIsAskedAndOffered.test.ts`.

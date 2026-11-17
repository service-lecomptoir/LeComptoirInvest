# Rotation de la cle des donnees chiffrees -- Le Comptoir Invest (IBAN) et Le Comptoir RH (IBAN, NIR).
#
# A lancer depuis PowerShell, sur le poste qui a les acces `ssh lecomptoir-vps` (serveur des
# applications) et `ssh lecomptoir-db` (serveur des bases) :
#
#   $OutputEncoding = New-Object System.Text.UTF8Encoding $false; .\rotation_cle_donnees.ps1 -Produit invest -Apercu
#
#   -Apercu            etat, rien n'est ecrit
#   -Expliciter        1re fois : la cle derivee de SECRET_KEY devient explicite
#   (sans option)      rotation : nouvelle cle en tete, rechiffrement, preuve
#   -RetirerAnciennes  2e temps : ne garder que la cle courante
#   -Rechiffrer        reprise : rechiffrer sans changer de cle
#
# (meme chose avec -Produit rh)
#
# Trois temps, et l'arret a la premiere erreur :
#   A. serveur des applications : verifications, RIEN n'est ecrit (l'apercu s'arrete la) ;
#   B. serveur des bases : sauvegarde de la base du produit, pg_dump -Fc dans le conteneur
#      bases_postgres, verifiee par pg_restore -l, dans ~/backups/rotation-cle de CE serveur ;
#   C. serveur des applications : les verifications de A refaites, puis
#      1. copie datee de backend/.env.prod (chmod 600) : elle garde l'ancienne cle, qui seule
#         ouvre les sauvegardes faites avant la rotation ;
#      2. ecriture du trousseau DATA_ENCRYPTION_KEYS (nouvelle cle en tete, ancienne en second) ;
#      3. recreation du conteneur serveur sur l'image qui tourne deja, et controle qu'il lit bien
#         le trousseau ecrit (par les empreintes courtes des cles, jamais les cles) ;
#      4. apercu, puis rechiffrement reel, puis preuve (python -m app.services.reencrypt).
#
# Depuis le 14 nov 2026 la base ne vit plus dans un conteneur du serveur des applications
# (les anciens conteneurs de base sont retires) : elle est sur le serveur des bases, dans bases_postgres.
# La sauvegarde et la copie de .env.prod portent le meme horodatage.
#
# Aucune cle ni aucune valeur en clair n'est affichee : seulement des comptes et des empreintes
# courtes (8 caracteres) qui designent une cle sans la reveler. Aucun mot de passe n'est lu
# ni demande : la sauvegarde passe par le compte administrateur local du conteneur.
param(
    [Parameter(Mandatory = $true)][ValidateSet("invest", "rh")][string]$Produit,
    [switch]$Apercu,
    [switch]$Expliciter,
    [switch]$RetirerAnciennes,
    [switch]$Rechiffrer
)

$modes = @(@($Apercu, $Expliciter, $RetirerAnciennes, $Rechiffrer) | Where-Object { $_ })
if ($modes.Count -gt 1) {
    Write-Host "ECHEC : une seule option parmi -Apercu, -Expliciter, -RetirerAnciennes, -Rechiffrer."
    exit 1
}
$Mode = "rotation"
if ($Apercu) { $Mode = "apercu" }
if ($Expliciter) { $Mode = "expliciter" }
if ($RetirerAnciennes) { $Mode = "retirer" }
if ($Rechiffrer) { $Mode = "rechiffrer" }

$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false

$App = "lecomptoir-vps"   # serveur des applications : le conteneur, .env.prod, le rechiffrement
$Db = "lecomptoir-db"     # serveur des bases : bases_postgres, la sauvegarde
# The product's base on the database server: the names of the nightly backup (Portail360,
# deploy/lecomptoir-backup.sh, REMOTE_DBS). Step A also checks it is the base DATABASE_URL
# names in backend/.env.prod, and step B that bases_postgres has it.
$Base = @{ invest = "lecomptoirinvest"; rh = "lecomptoirrh" }[$Produit]
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

# --- Serveur des applications : verifications (etape A), puis ecritures (etape C). ---
$appScript = @'
set -eu
PRODUIT="$1"; MODE="$2"; ETAPE="$3"; BASE="$4"; STAMP="$5"
case "$PRODUIT" in
  invest) REPO="$HOME/LeComptoirInvest"; PROJET=invest; SERVICE=invest-backend; API=invest_backend ;;
  rh)     REPO="$HOME/LeComptoirRH";     PROJET=rh;     SERVICE=rh-api;         API=rh_api ;;
  *) echo "ECHEC : produit inconnu ($PRODUIT)"; exit 1 ;;
esac
ENVF="$REPO/backend/.env.prod"
VAR=DATA_ENCRYPTION_KEYS

die() { echo "ECHEC : $*"; exit 1; }
keyid() { printf %s "$1" | sha256sum | cut -c1-8; }
ids_of() { for k in $(printf %s "$1" | tr ',' ' '); do keyid "$k"; done | tr '\n' ' ' | sed 's/ $//'; }
# Le trousseau ecrit dans le fichier, jamais affiche.
ring_in_file() { grep -E "^${VAR}=" "$ENVF" | tail -n 1 | cut -d= -f2- | tr -d "\"' \r" || true; }
# Le nom de la base que vise DATABASE_URL (le nom seul, jamais le reste de l'adresse).
base_in_file() { grep -E "^DATABASE_URL=" "$ENVF" | tail -n 1 | cut -d= -f2- | tr -d "\"' \r" | sed -E 's#^[^/]*//[^/]*/##; s#[?].*$##' || true; }
# Ce que le conteneur lit : nombre de cles, explicite ou derivee, empreintes courtes.
ring_seen() { docker exec "$API" python -c 'from app.core import crypto; r = crypto.keyring(); print(" ".join(crypto.key_id(k) for k in r))'; }
explicit_seen() { docker exec "$API" python -c 'from app.core import crypto; print(1 if crypto.is_explicit() else 0)'; }
run_pass() { docker exec "$API" python -m app.services.reencrypt "$@"; }

[ -f "$ENVF" ] || die "$ENVF absent"
docker inspect "$API" >/dev/null 2>&1 || die "conteneur $API absent"
[ "$(base_in_file)" = "$BASE" ] || die "DATABASE_URL de .env.prod vise la base [$(base_in_file)], la sauvegarde viserait [$BASE] : rien n'est fait"

# Etape A : tout est verifie, rien n'est ecrit ; la sauvegarde passe ensuite sur le serveur
# des bases. Etape C : la sauvegarde est faite, les ecritures commencent.
ready() {
  if [ "$ETAPE" = verifier ]; then
    echo "PRET : verifications faites, rien n'est ecrit. Suite : sauvegarde de la base $BASE sur le serveur des bases."
    exit 0
  fi
  echo "Sauvegarde faite sur le serveur des bases (~/backups/rotation-cle/${PRODUIT}_${STAMP}.dump) : les ecritures commencent."
}
save_env() {
  ENV_BACKUP="$ENVF.avant-cle-$STAMP"
  cp -p "$ENVF" "$ENV_BACKUP"; chmod 600 "$ENV_BACKUP"
  echo "OK copie de .env.prod : $ENV_BACKUP (chmod 600)"
}
write_ring() {  # $1 = trousseau complet, jamais affiche
  tmp=$(mktemp "$ENVF.tmp.XXXXXX"); chmod 600 "$tmp"
  RING="$1" awk -v var="$VAR" '
    index($0, var "=") == 1 { if (!done) { print var "=" ENVIRON["RING"]; done = 1 } ; next }
    { print }
    END { if (!done) print var "=" ENVIRON["RING"] }' "$ENVF" > "$tmp"
  mv "$tmp" "$ENVF"; chmod 600 "$ENVF"
  [ "$(ring_in_file)" = "$1" ] || die "le trousseau relu dans .env.prod n'est pas celui ecrit"
  echo "OK $VAR ecrite dans .env.prod : $(printf %s "$1" | tr ',' '\n' | grep -c .) cle(s), empreintes $(ids_of "$1")"
}
recreate() {
  img=$(docker inspect "$API" --format '{{.Config.Image}}')
  export IMAGE_TAG="${img##*:}"
  ( cd "$REPO" && docker compose -p "$PROJET" -f docker/docker-compose.deploy.yml up -d --force-recreate --no-deps --pull never "$SERVICE" </dev/null ) || die "recreation de $SERVICE"
  st=starting; i=0
  while [ "$i" -lt 60 ]; do
    st=$(docker inspect "$API" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')
    [ "$st" = healthy ] && break
    sleep 3; i=$((i+1))
  done
  [ "$st" = healthy ] || die "le conteneur $API n'est pas reparti sain ($st) ; journal : docker logs --tail 50 $API"
  echo "OK conteneur $API recree sur l'image $IMAGE_TAG (sain)"
}
check_seen() {  # $1 = trousseau attendu
  want=$(ids_of "$1"); seen=$(ring_seen)
  [ "$seen" = "$want" ] || die "le conteneur lit les cles [$seen] au lieu de [$want]"
  [ "$(explicit_seen)" = 1 ] || die "le conteneur ne voit pas $VAR"
  echo "OK le conteneur lit le trousseau ecrit : [$seen], la premiere chiffre"
}
reencrypt_and_prove() {
  echo "--- apercu ---"
  run_pass --apercu || die "l'apercu signale des valeurs illisibles : rien n'a ete rechiffre"
  echo "--- rechiffrement et preuve ---"
  run_pass || die "le rechiffrement ou sa preuve a echoue (toutes les cles restent dans le trousseau : aucune donnee n'est perdue ; relancer avec -Rechiffrer)"
}

FILE_RING=$(ring_in_file)
echo "Produit : $PRODUIT ; conteneur : $API ; image : $(docker inspect "$API" --format '{{.Config.Image}}') ; base : $BASE (serveur des bases)"
if [ -n "$FILE_RING" ]; then
  echo "$VAR dans .env.prod : $(printf %s "$FILE_RING" | tr ',' '\n' | grep -c .) cle(s), empreintes $(ids_of "$FILE_RING")"
else
  echo "$VAR absente de .env.prod : la cle est encore derivee de SECRET_KEY"
fi
echo "Le conteneur lit : [$(ring_seen)] ($( [ "$(explicit_seen)" = 1 ] && echo explicite || echo derivee de SECRET_KEY ))"
# Le fichier et le conteneur doivent dire la meme chose avant toute ecriture.
if [ -n "$FILE_RING" ]; then
  [ "$(ring_seen)" = "$(ids_of "$FILE_RING")" ] || die "le conteneur ne lit pas le trousseau du fichier : recreez-le d'abord, puis relancez"
else
  [ "$(explicit_seen)" = 0 ] || die "le conteneur voit $VAR alors que .env.prod ne la contient pas"
fi

case "$MODE" in
  apercu)
    run_pass --apercu || die "des valeurs ne s'ouvrent avec aucune cle"
    echo "Apercu termine : rien n'a ete ecrit."
    ;;

  expliciter)
    if [ -n "$FILE_RING" ]; then
      echo "DEJA FAIT : $VAR est deja explicite. Rien n'est modifie."
      exit 10
    fi
    run_pass --apercu || die "des valeurs sont deja illisibles avec la cle actuelle : rien n'est modifie"
    K0=$(docker exec "$API" python -c 'import sys; from app.core import crypto; sys.stdout.write(crypto.legacy_key())')
    [ "$(keyid "$K0")" = "$(ring_seen)" ] || die "la cle derivee ne correspond pas a celle que lit le conteneur"
    ready
    save_env
    write_ring "$K0"
    recreate; check_seen "$K0"
    reencrypt_and_prove
    echo "TERMINE : la cle est explicite. Changer SECRET_KEY ne touche plus les donnees chiffrees."
    ;;

  rotation)
    run_pass --apercu || die "des valeurs sont deja illisibles avec le trousseau actuel : rien n'est modifie"
    if [ -n "$FILE_RING" ]; then
      RING0="$FILE_RING"
    else
      RING0=$(docker exec "$API" python -c 'import sys; from app.core import crypto; sys.stdout.write(crypto.legacy_key())')
      [ "$(keyid "$RING0")" = "$(ring_seen)" ] || die "la cle derivee ne correspond pas a celle que lit le conteneur"
      echo "La cle derivee de SECRET_KEY est d'abord rendue explicite (elle reste en second)."
    fi
    ready
    KN=$(docker exec "$API" python -c 'import sys; from cryptography.fernet import Fernet; sys.stdout.write(Fernet.generate_key().decode())')
    [ -n "$KN" ] || die "la nouvelle cle n'a pas pu etre generee"
    save_env
    write_ring "$KN,$RING0"
    recreate; check_seen "$KN,$RING0"
    reencrypt_and_prove
    echo "TERMINE : nouvelle cle $(keyid "$KN") en tete, les anciennes restent en second."
    echo "Quand vous le decidez : relancez avec -RetirerAnciennes pour ne garder que la cle courante."
    ;;

  rechiffrer)
    ready
    reencrypt_and_prove
    echo "TERMINE : tout est sur la cle courante."
    ;;

  retirer)
    [ -n "$FILE_RING" ] || die "$VAR absente : rien a retirer (lancez d'abord -Expliciter)"
    n=$(printf %s "$FILE_RING" | tr ',' '\n' | grep -c .)
    if [ "$n" -le 1 ]; then echo "DEJA FAIT : une seule cle dans le trousseau. Rien n'est modifie."; exit 10; fi
    run_pass --verifier || die "des valeurs ne s'ouvrent pas encore avec la cle courante seule : lancez d'abord -Rechiffrer"
    FIRST="${FILE_RING%%,*}"
    ready
    save_env
    write_ring "$FIRST"
    recreate; check_seen "$FIRST"
    if ! run_pass --verifier; then
      echo "Retour arriere : l'ancien trousseau est remis."
      cp -p "$ENV_BACKUP" "$ENVF"; chmod 600 "$ENVF"; recreate
      die "apres retrait, une valeur ne s'ouvrait plus ; le trousseau complet est remis"
    fi
    echo "TERMINE : seule la cle $(keyid "$FIRST") reste. Les anciennes sont dans $ENV_BACKUP :"
    echo "gardez ce fichier tant que des sauvegardes de la base faites avant la rotation existent."
    ;;

  *) die "mode inconnu ($MODE)" ;;
esac
# fin
'@

# --- Serveur des bases : la sauvegarde (etape B), dans bases_postgres. ---
$dbScript = @'
set -eu
umask 077
PRODUIT="$1"; BASE="$2"; STAMP="$3"
die() { echo "ECHEC : $*"; exit 1; }
docker inspect bases_postgres >/dev/null 2>&1 || die "conteneur bases_postgres absent du serveur des bases"
n=$(docker exec bases_postgres psql -U lecomptoir_admin -d postgres -AtXc "SELECT count(*) FROM pg_database WHERE datname = '$BASE'") || die "bases_postgres ne repond pas"
[ "$n" = 1 ] || die "la base $BASE n'existe pas sur le serveur des bases"
dir="$HOME/backups/rotation-cle"; mkdir -p "$dir"; chmod 700 "$dir"
out="$dir/${PRODUIT}_${STAMP}.dump"
[ ! -e "$out" ] || die "$out existe deja"
if ! docker exec bases_postgres pg_dump -U lecomptoir_admin -Fc -d "$BASE" > "$out"; then
  rm -f "$out"; die "pg_dump a echoue (base $BASE)"
fi
chmod 600 "$out"
[ -s "$out" ] || { rm -f "$out"; die "sauvegarde vide : $out"; }
listing=$(docker exec -i bases_postgres pg_restore -l < "$out") || die "sauvegarde illisible par pg_restore : $out"
tables=$(printf '%s\n' "$listing" | grep -c ' TABLE DATA ' || true)
[ "$tables" -gt 0 ] || die "la sauvegarde ne contient aucune table : $out"
echo "OK sauvegarde de la base $BASE sur le serveur des bases : $out ($(du -h "$out" | cut -f1), $tables tables)"
'@

# The script is sent on stdin, its carriage returns removed, saved to a file and run with
# stdin closed: a command of the script that reads stdin can never swallow the rest of it.
function Invoke-OnServer([string]$HostAlias, [string]$Script, [string]$Arguments) {
    $shell = 'f=$(mktemp) && tr -d ''\r'' > $f && bash $f ' + $Arguments + ' </dev/null; rc=$?; rm -f $f; exit $rc'
    $Script | ssh -o BatchMode=yes -o ConnectTimeout=15 $HostAlias $shell | Out-Host
    return $LASTEXITCODE
}
function Stop-OnFailure([int]$Code, [string]$What) {
    Write-Host ""
    Write-Host "ECHEC (code $Code) pendant $What : lisez la ligne ECHEC ci-dessus. Aucune etape suivante n'a ete lancee."
    exit $Code
}

Write-Host "=== A. Serveur des applications ($App) : verifications, rien n'est ecrit ==="
$rc = Invoke-OnServer $App $appScript "$Produit $Mode verifier $Base $Stamp"
if ($rc -eq 10) { exit 0 }
if ($rc -ne 0) { Stop-OnFailure $rc "les verifications" }
if ($Mode -eq "apercu") { exit 0 }

Write-Host ""
Write-Host "=== B. Serveur des bases ($Db) : sauvegarde de la base $Base ==="
$rc = Invoke-OnServer $Db $dbScript "$Produit $Base $Stamp"
if ($rc -ne 0) { Stop-OnFailure $rc "la sauvegarde (rien n'a ete ecrit sur le serveur des applications)" }

Write-Host ""
Write-Host "=== C. Serveur des applications ($App) : ecritures ==="
$rc = Invoke-OnServer $App $appScript "$Produit $Mode ecrire $Base $Stamp"
if ($rc -eq 10) { exit 0 }
if ($rc -ne 0) { Stop-OnFailure $rc "les ecritures" }

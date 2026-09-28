# Rotation de la cle des donnees chiffrees -- Le Comptoir Invest (IBAN) et Le Comptoir RH (IBAN, NIR).
#
# A lancer depuis PowerShell, sur le poste qui a l'acces `ssh lecomptoir-vps` :
#
#   .\rotation_cle_donnees.ps1 -Produit invest -Apercu            etat, rien n'est ecrit
#   .\rotation_cle_donnees.ps1 -Produit invest -Expliciter        1re fois : la cle derivee de SECRET_KEY devient explicite
#   .\rotation_cle_donnees.ps1 -Produit invest                    rotation : nouvelle cle en tete, rechiffrement, preuve
#   .\rotation_cle_donnees.ps1 -Produit invest -RetirerAnciennes  2e temps : ne garder que la cle courante
#   .\rotation_cle_donnees.ps1 -Produit invest -Rechiffrer        reprise : rechiffrer sans changer de cle
#
# (meme chose avec -Produit rh)
#
# Ce que fait chaque etape qui ecrit, dans cet ordre, et s'arrete a la premiere erreur :
#   1. sauvegarde de la base (pg_dump -Fc, verifiee par pg_restore -l) dans ~/backups/rotation-cle ;
#   2. copie datee de backend/.env.prod (chmod 600) : elle garde l'ancienne cle, qui seule ouvre
#      les sauvegardes faites avant la rotation ;
#   3. ecriture du trousseau DATA_ENCRYPTION_KEYS (nouvelle cle en tete, ancienne en second) ;
#   4. recreation du conteneur serveur sur l'image qui tourne deja, et controle qu'il lit bien
#      le trousseau ecrit (par les empreintes courtes des cles, jamais les cles) ;
#   5. apercu, puis rechiffrement reel, puis preuve (python -m app.services.reencrypt).
#
# Aucune cle ni aucune valeur en clair n'est affichee : seulement des comptes et des empreintes
# courtes (8 caracteres) qui designent une cle sans la reveler.
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

$script = @'
set -eu
PRODUIT="$1"; MODE="$2"
case "$PRODUIT" in
  invest) REPO="$HOME/LeComptoirInvest"; PROJET=invest; SERVICE=invest-backend; API=invest_backend; DB=invest_db ;;
  rh)     REPO="$HOME/LeComptoirRH";     PROJET=rh;     SERVICE=rh-api;         API=rh_api;         DB=rh_db ;;
  *) echo "ECHEC : produit inconnu ($PRODUIT)"; exit 1 ;;
esac
ENVF="$REPO/backend/.env.prod"
VAR=DATA_ENCRYPTION_KEYS
STAMP=$(date +%Y%m%d-%H%M%S)

die() { echo "ECHEC : $*"; exit 1; }
keyid() { printf %s "$1" | sha256sum | cut -c1-8; }
ids_of() { for k in $(printf %s "$1" | tr ',' ' '); do keyid "$k"; done | tr '\n' ' ' | sed 's/ $//'; }
# Le trousseau ecrit dans le fichier, jamais affiche.
ring_in_file() { grep -E "^${VAR}=" "$ENVF" | tail -n 1 | cut -d= -f2- | tr -d "\"' \r" || true; }
# Ce que le conteneur lit : nombre de cles, explicite ou derivee, empreintes courtes.
ring_seen() { docker exec "$API" python -c 'from app.core import crypto; r = crypto.keyring(); print(" ".join(crypto.key_id(k) for k in r))'; }
explicit_seen() { docker exec "$API" python -c 'from app.core import crypto; print(1 if crypto.is_explicit() else 0)'; }
run_pass() { docker exec "$API" python -m app.services.reencrypt "$@"; }

[ -f "$ENVF" ] || die "$ENVF absent"
docker inspect "$API" >/dev/null 2>&1 || die "conteneur $API absent"
docker inspect "$DB" >/dev/null 2>&1 || die "conteneur $DB absent"

save_db() {
  dir="$HOME/backups/rotation-cle"; mkdir -p "$dir"; chmod 700 "$dir"
  out="$dir/${PRODUIT}_${STAMP}.dump"
  docker exec "$DB" sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$out" || die "pg_dump a echoue"
  chmod 600 "$out"
  [ -s "$out" ] || die "sauvegarde vide : $out"
  docker exec -i "$DB" pg_restore -l < "$out" > /dev/null || die "sauvegarde illisible par pg_restore : $out"
  echo "OK sauvegarde de la base : $out ($(du -h "$out" | cut -f1))"
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
echo "Produit : $PRODUIT ; conteneur : $API ; image : $(docker inspect "$API" --format '{{.Config.Image}}')"
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
      exit 0
    fi
    run_pass --apercu || die "des valeurs sont deja illisibles avec la cle actuelle : rien n'est modifie"
    K0=$(docker exec "$API" python -c 'import sys; from app.core import crypto; sys.stdout.write(crypto.legacy_key())')
    [ "$(keyid "$K0")" = "$(ring_seen)" ] || die "la cle derivee ne correspond pas a celle que lit le conteneur"
    save_db; save_env
    write_ring "$K0"
    recreate; check_seen "$K0"
    reencrypt_and_prove
    echo "TERMINE : la cle est explicite. Changer SECRET_KEY ne touche plus les donnees chiffrees."
    ;;

  rotation)
    run_pass --apercu || die "des valeurs sont deja illisibles avec le trousseau actuel : rien n'est modifie"
    if [ -n "$FILE_RING" ]; then
      BASE="$FILE_RING"
    else
      BASE=$(docker exec "$API" python -c 'import sys; from app.core import crypto; sys.stdout.write(crypto.legacy_key())')
      [ "$(keyid "$BASE")" = "$(ring_seen)" ] || die "la cle derivee ne correspond pas a celle que lit le conteneur"
      echo "La cle derivee de SECRET_KEY est d'abord rendue explicite (elle reste en second)."
    fi
    KN=$(docker exec "$API" python -c 'import sys; from cryptography.fernet import Fernet; sys.stdout.write(Fernet.generate_key().decode())')
    [ -n "$KN" ] || die "la nouvelle cle n'a pas pu etre generee"
    save_db; save_env
    write_ring "$KN,$BASE"
    recreate; check_seen "$KN,$BASE"
    reencrypt_and_prove
    echo "TERMINE : nouvelle cle $(keyid "$KN") en tete, les anciennes restent en second."
    echo "Quand vous le decidez : relancez avec -RetirerAnciennes pour ne garder que la cle courante."
    ;;

  rechiffrer)
    save_db
    reencrypt_and_prove
    echo "TERMINE : tout est sur la cle courante."
    ;;

  retirer)
    [ -n "$FILE_RING" ] || die "$VAR absente : rien a retirer (lancez d'abord -Expliciter)"
    n=$(printf %s "$FILE_RING" | tr ',' '\n' | grep -c .)
    if [ "$n" -le 1 ]; then echo "DEJA FAIT : une seule cle dans le trousseau. Rien n'est modifie."; exit 0; fi
    run_pass --verifier || die "des valeurs ne s'ouvrent pas encore avec la cle courante seule : lancez d'abord -Rechiffrer"
    FIRST="${FILE_RING%%,*}"
    save_db; save_env
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

$b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script.Replace("`r`n", "`n")))
ssh lecomptoir-vps "echo $b64 | base64 -d | bash -s -- $Produit $Mode"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ECHEC (code $LASTEXITCODE) : lisez la ligne ECHEC ci-dessus. Aucune etape suivante n'a ete lancee."
    exit $LASTEXITCODE
}

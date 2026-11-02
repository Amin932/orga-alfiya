#!/bin/sh
# Sauvegarde cohérente PostgreSQL + pièces jointes ; exécuter : sudo sh scripts/backup_nas.sh
set -eu
umask 077
cd "$(dirname "$0")/.."
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="${BACKUP_DIR:-$(pwd)/backups}"
mkdir -p "$backup_dir"
final="$backup_dir/$timestamp"
temporary="$backup_dir/.$timestamp.partial"
if [ -e "$final" ] || [ -e "$temporary" ]; then
  echo "Dossier de sauvegarde déjà existant" >&2; exit 1
fi
mkdir "$temporary"
maintenance=0
restore_services() {
  if [ "$maintenance" = 1 ]; then
    echo "Redémarrage des services..."
    docker compose up -d api notification-worker web >/dev/null || echo "ALERTE : redémarrage impossible" >&2
  fi
}
on_exit() {
  restore_services
  if [ -d "$temporary" ]; then rm -rf "$temporary"; fi
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "Arrêt temporaire du site, API et worker."
maintenance=1
docker compose stop web notification-worker api
echo "Sauvegarde PostgreSQL..."
docker compose exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$temporary/database.dump"
echo "Sauvegarde des documents..."
docker compose run --no-deps --rm -T --entrypoint python api -c \
  "import tarfile,sys; t=tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz'); t.add('/app/uploads',arcname='uploads'); t.close()" \
  > "$temporary/uploads.tar.gz"
echo "Contrôle des archives..."
[ -s "$temporary/database.dump" ] && [ -s "$temporary/uploads.tar.gz" ]
docker compose exec -T db pg_restore --list < "$temporary/database.dump" > /dev/null
gzip -t "$temporary/uploads.tar.gz"
printf '%s\n' "Sauvegarde UTC : $timestamp" "Orga Alfiya" > "$temporary/README.txt"
if command -v sha256sum >/dev/null 2>&1; then
  (cd "$temporary" && sha256sum database.dump uploads.tar.gz > SHA256SUMS)
fi
mv "$temporary" "$final"
echo "Sauvegarde créée : $final"
echo "IMPORTANT : copier vers un support externe chiffré, puis tester une restauration."

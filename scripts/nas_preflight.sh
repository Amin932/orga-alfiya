#!/bin/sh
# Vérifie la configuration sans afficher les valeurs sensibles.
set -eu
cd "$(dirname "$0")/.."
if ! command -v docker >/dev/null 2>&1; then
  echo "ERREUR : commande Docker indisponible." >&2; exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "ERREUR : plugin 'docker compose' absent ou inaccessible." >&2; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "ERREUR : pas d'accès au daemon Docker (sudo peut être nécessaire)." >&2; exit 1
fi
if [ ! -f .env ]; then
  echo "ERREUR : fichier .env manquant. Copier .env.example, puis le configurer." >&2; exit 1
fi
if grep -Eq 'REMPLACER|admin@example.com|smtp.example.com' .env; then
  echo "ERREUR : des exemples ou des secrets factices restent dans .env." >&2; exit 1
fi
if grep -Eq '^COOKIE_SECURE=false' .env; then
  echo "ERREUR : COOKIE_SECURE doit rester à true pour HTTPS." >&2; exit 1
fi
if ! docker compose config --quiet; then
  echo "ERREUR : la configuration Compose contient une erreur." >&2; exit 1
fi
if [ ! -f secrets/vapid_private.pem ]; then
  echo "AVERTISSEMENT : clé VAPID absente, le push sera indisponible."
fi
echo "OK : Docker et variables Compose valides (aucune donnée sensible affichée)."
echo "Attention : DNS, HTTPS, ouverture des ports et SMTP doivent aussi être testés."

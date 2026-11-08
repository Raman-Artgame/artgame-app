#!/usr/bin/env bash
# Ночная копия базы одного окружения: backup.sh test|prod
# pg_dump → gzip → /var/backups/artgame-app/<env>/, храним 14 дней.
# Если в /etc/artgame-app/<env>.env задан BACKUP_DRIVE_FOLDER — копия ещё и на Google Диск (сервисный аккаунт).
# Метка последней удачной копии: /var/backups/artgame-app/<env>/LAST_OK (для Стража и /api/health не нужна).
set -euo pipefail
ENV=${1:?test|prod}
case "$ENV" in test|prod) ;; *) echo "только test или prod" >&2; exit 2 ;; esac
: "${ARTGAME_DATABASE_URL:?нет ARTGAME_DATABASE_URL в /etc/artgame-app/$ENV.env}"
DIR=/var/backups/artgame-app/$ENV
mkdir -p "$DIR"; chmod 750 "$DIR"
F="$DIR/artgame-$ENV-$(date +%F).sql.gz"
TMP="$F.part"
trap 'rm -f "$TMP"' EXIT
umask 027
pg_dump --no-owner --no-privileges "$ARTGAME_DATABASE_URL" | gzip -9 > "$TMP"
gzip -t "$TMP"
[ "$(stat -c %s "$TMP")" -gt 1024 ] || { echo "копия подозрительно мала" >&2; rm -f "$TMP"; exit 1; }
mv "$TMP" "$F"
if [ -n "${BACKUP_DRIVE_FOLDER:-}" ]; then
  "/srv/artgame-app/$ENV/venv/bin/python" "/srv/artgame-app/$ENV/deploy/upload_drive.py" "$F"
else
  echo "BACKUP_DRIVE_FOLDER не задан — копия только на сервере"
fi
date -Is > "$DIR/LAST_OK"
find "$DIR" -name 'artgame-*.sql.gz' -mtime +14 -print -delete
echo "копия готова: $F ($(stat -c %s "$F") байт)"

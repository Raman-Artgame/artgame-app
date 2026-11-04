#!/usr/bin/env bash
# Ночная копия: pg_dump → gzip → Google Диск (папка из BACKUP_DRIVE_FOLDER), локально храним 14 дней.
set -euo pipefail
DIR=/var/backups/artgame-app
mkdir -p "$DIR"
F="$DIR/artgame-$(date +%F).sql.gz"
pg_dump --no-owner "$DATABASE_URL" | gzip -9 > "$F"
test -s "$F"
/srv/artgame-app/prod/venv/bin/python /srv/artgame-app/prod/deploy/upload_drive.py "$F"
find "$DIR" -name 'artgame-*.sql.gz' -mtime +14 -print -exec rm {} \;

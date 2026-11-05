#!/usr/bin/env bash
# Выкладка одного окружения из папки app/ репозитория: sudo app/deploy/deploy.sh test|prod
# Собирает экран (npm), ставит зависимости API в venv, перезапускает службы, проверяет /api/health.
set -euo pipefail
ENV=${1:?test|prod}
case "$ENV" in test|prod) ;; *) echo "только test или prod" >&2; exit 2 ;; esac
SRC=$(cd "$(dirname "$0")/.." && pwd)
DST=/srv/artgame-app/$ENV
test -f "/etc/artgame-app/$ENV.env" || { echo "нет /etc/artgame-app/$ENV.env (см. env.example)" >&2; exit 1; }

# Экран: сборка во временной папке, чтобы не мусорить в репозитории
BUILD=$(mktemp -d)
trap 'rm -rf "$BUILD"' EXIT
rsync -a --exclude node_modules --exclude dist "$SRC/frontend/" "$BUILD/"
(cd "$BUILD" && npm ci --no-audit --no-fund && npm run build)
test -f "$BUILD/dist/index.html"

install -d -o artgame-app -g artgame-app "$DST"
rsync -a --delete --exclude .venv --exclude __pycache__ --exclude .pytest_cache "$SRC/backend/" "$DST/backend/"
rsync -a --delete "$BUILD/dist/" "$DST/web/"
rsync -a --delete "$SRC/deploy/" "$DST/deploy/"
[ -x "$DST/venv/bin/python" ] || python3 -m venv "$DST/venv"
"$DST/venv/bin/pip" install -q -r "$DST/backend/requirements.txt"
chown -R artgame-app:artgame-app "$DST"
chmod 755 /srv/artgame-app "$DST"; chmod -R a+rX "$DST/web"   # Caddy читает web/ при любом umask

install -m 644 "$SRC"/deploy/artgame-*.service "$SRC"/deploy/artgame-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "artgame-api@$ENV" "artgame-constants@$ENV.timer" "artgame-objects@$ENV.timer" "artgame-notify@$ENV.timer"
systemctl restart "artgame-api@$ENV"
if [ "$ENV" = prod ]; then systemctl enable --now artgame-backup.timer; fi

PORT=$(grep '^PORT=' "/etc/artgame-app/$ENV.env" | cut -d= -f2)
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://127.0.0.1:$PORT/api/health"; then echo " — $ENV выложен"; exit 0; fi
  sleep 2
done
journalctl -u "artgame-api@$ENV" -n 50 --no-pager >&2
exit 1

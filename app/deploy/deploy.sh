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
# Старые assets/ оставляем на 14 дней: Telegram и браузеры кэшируют index.html и после выкладки тянут старые
# имена файлов — без этого экран пустой, пока кэш не сбросят (HEAD 06.11).
if [ -d "$DST/web/assets" ]; then
  find "$DST/web/assets" -type f -mtime +14 -delete || true
  rsync -a --ignore-existing "$DST/web/assets/" "$BUILD/dist/assets/"
fi
rsync -a --delete "$BUILD/dist/" "$DST/web/"
# Заголовки кэша в Caddy (index.html не кэшировать, assets — навсегда): обновляем файл сайта, если он отстал от репозитория
if [ -f /etc/caddy/artgame-app.caddy ] && ! cmp -s "$SRC/deploy/Caddyfile" /etc/caddy/artgame-app.caddy; then
  install -m 644 "$SRC/deploy/Caddyfile" /etc/caddy/artgame-app.caddy
  CF=$(ps -o args= -C caddy | sed -n 's/.*--config \([^ ]*\).*/\1/p' | head -1)
  caddy reload --config "${CF:-/etc/caddy/Caddyfile}" --adapter caddyfile 2>/dev/null \
    || systemctl reload ARTGAME-MCP-https 2>/dev/null || systemctl reload caddy 2>/dev/null \
    || echo "Caddy не перечитал конфиг — заголовки кэша появятся после перезапуска Caddy" >&2
fi
rsync -a --delete "$SRC/deploy/" "$DST/deploy/"
[ -x "$DST/venv/bin/python" ] || python3 -m venv "$DST/venv"
"$DST/venv/bin/pip" install -q -r "$DST/backend/requirements.txt"
chown -R artgame-app:artgame-app "$DST"
chmod 755 /srv/artgame-app "$DST"; chmod -R a+rX "$DST/web"   # Caddy читает web/ при любом umask

install -m 644 "$SRC"/deploy/artgame-*.service "$SRC"/deploy/artgame-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "artgame-api@$ENV" "artgame-constants@$ENV.timer" "artgame-objects@$ENV.timer" "artgame-notify@$ENV.timer" "artgame-finexport@$ENV.timer"
systemctl restart "artgame-api@$ENV"
# Ночная копия базы — для каждого окружения (команда работает на test с 09.11). Старый общий таймер только для prod убран.
systemctl disable --now artgame-backup.timer 2>/dev/null || true
rm -f /etc/systemd/system/artgame-backup.service /etc/systemd/system/artgame-backup.timer
systemctl daemon-reload
systemctl enable --now "artgame-backup@$ENV.timer"

PORT=$(grep '^PORT=' "/etc/artgame-app/$ENV.env" | cut -d= -f2)
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://127.0.0.1:$PORT/api/health"; then echo " — $ENV выложен"; exit 0; fi
  sleep 2
done
journalctl -u "artgame-api@$ENV" -n 50 --no-pager >&2
exit 1

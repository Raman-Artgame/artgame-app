#!/usr/bin/env bash
# Однократная подготовка VPS: sudo app/deploy/bootstrap.sh. Повторный запуск безопасен.
# Шлюз mcp.artgame.world и задачи SRC02/DRIVE01/FIN03 не трогает: Caddyfile только дополняется одной строкой import.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)

apt-get update
apt-get install -y postgresql-16 python3-venv python3-pip rsync nodejs npm curl
command -v caddy >/dev/null || pgrep -x caddy >/dev/null || apt-get install -y caddy

id artgame-app >/dev/null 2>&1 || useradd --system --create-home --home-dir /srv/artgame-app --shell /usr/sbin/nologin artgame-app
install -d -o artgame-app -g artgame-app -m 755 /srv/artgame-app
install -d -o artgame-app -g artgame-app -m 750 /var/log/artgame-app /var/backups/artgame-app
install -d -o root -g artgame-app -m 750 /etc/artgame-app

sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='artgame-app'" | grep -q 1 || sudo -u postgres createuser artgame-app
for db in artgame_prod artgame_test; do
  sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 || sudo -u postgres createdb -O artgame-app "$db"
  sudo -u postgres psql -d "$db" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto"
done

# Caddy: сайты приложения отдельным файлом. Подключаем к тому Caddy, который уже держит 443
# (на VPS это ARTGAME-MCP-https с /etc/artgame-mcp/Caddyfile), одной строкой import с копией.
install -m 644 "$HERE/Caddyfile" /etc/caddy/artgame-app.caddy 2>/dev/null || { install -d -m 755 /etc/caddy; install -m 644 "$HERE/Caddyfile" /etc/caddy/artgame-app.caddy; }
CF=$(ps -o args= -C caddy | sed -n 's/.*--config \([^ ]*\).*/\1/p' | head -1)
CF=${CF:-/etc/caddy/Caddyfile}
echo "Caddy: $CF"
if ! grep -q '^import /etc/caddy/artgame-app.caddy' "$CF"; then
  cp -a "$CF" "$CF.bak-$(date +%Y%m%d%H%M%S)"
  printf '\nimport /etc/caddy/artgame-app.caddy\n' >> "$CF"
fi
if ! caddy validate --config "$CF" --adapter caddyfile >/tmp/artgame-caddy-validate.log 2>&1; then
  cat /tmp/artgame-caddy-validate.log >&2
  B=$(ls -t "$CF".bak-* | head -1); cp -a "$B" "$CF"; echo "Caddyfile вернул из $B" >&2; exit 1
fi
if pgrep -x caddy >/dev/null; then
  U=$(ps -o unit= -p "$(pgrep -x caddy | head -1)" | tr -d ' ')
  caddy reload --config "$CF" --adapter caddyfile || systemctl reload "$U" || systemctl restart "$U"
else
  systemctl reload-or-restart caddy
fi

echo "Дальше: /etc/artgame-app/test.env по env.example (PORT=8101, ARTGAME_ENV_NAME=test, база artgame_test), затем app/deploy/deploy.sh test"

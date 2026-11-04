#!/usr/bin/env bash
# Однократная подготовка VPS: sudo app/deploy/bootstrap.sh. Повторный запуск безопасен.
# Шлюз mcp.artgame.world и задачи SRC02/DRIVE01/FIN03 не трогает: Caddyfile только дополняется одной строкой import.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)

apt-get update
apt-get install -y postgresql-16 python3-venv python3-pip rsync nodejs npm curl
command -v caddy >/dev/null || apt-get install -y caddy

id artgame-app >/dev/null 2>&1 || useradd --system --create-home --home-dir /srv/artgame-app --shell /usr/sbin/nologin artgame-app
install -d -o artgame-app -g artgame-app -m 755 /srv/artgame-app
install -d -o artgame-app -g artgame-app -m 750 /var/log/artgame-app /var/backups/artgame-app
install -d -o root -g artgame-app -m 750 /etc/artgame-app

sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='artgame-app'" | grep -q 1 || sudo -u postgres createuser artgame-app
for db in artgame_prod artgame_test; do
  sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 || sudo -u postgres createdb -O artgame-app "$db"
  sudo -u postgres psql -d "$db" -c "CREATE EXTENSION IF NOT EXISTS pgcrypto"
done

# Caddy: сайты приложения отдельным файлом, основной Caddyfile только дополняем строкой import (с копией)
CF=/etc/caddy/Caddyfile
install -m 644 "$HERE/Caddyfile" /etc/caddy/artgame-app.caddy
if ! grep -q '^import /etc/caddy/artgame-app.caddy' "$CF"; then
  cp -a "$CF" "$CF.bak-$(date +%Y%m%d%H%M%S)"
  printf '\nimport /etc/caddy/artgame-app.caddy\n' >> "$CF"
fi
caddy validate --config "$CF" --adapter caddyfile
systemctl reload caddy

echo "Дальше: /etc/artgame-app/test.env по env.example (PORT=8101, ARTGAME_ENV_NAME=test, база artgame_test), затем app/deploy/deploy.sh test"

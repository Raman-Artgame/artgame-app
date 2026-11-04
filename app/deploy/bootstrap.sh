#!/usr/bin/env bash
# Однократная подготовка VPS (запускает deploy-admin через sudo). Повторный запуск безопасен.
# Шлюз mcp.artgame.world и задачи SRC02/DRIVE01/FIN03 не трогает.
set -euo pipefail

apt-get update
apt-get install -y postgresql-16 python3-venv python3-pip caddy rsync

id artgame-app >/dev/null 2>&1 || useradd --system --create-home --home-dir /srv/artgame-app --shell /usr/sbin/nologin artgame-app
install -d -o artgame-app -g artgame-app -m 750 /srv/artgame-app/{prod,test} /var/log/artgame-app /var/backups/artgame-app
install -d -o root -g artgame-app -m 750 /etc/artgame-app

for db in artgame_prod artgame_test; do
  sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='artgame-app'" | grep -q 1 || sudo -u postgres createuser artgame-app
  sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$db'" | grep -q 1 || sudo -u postgres createdb -O artgame-app "$db"
done
sudo -u postgres psql -d artgame_prod -c "CREATE EXTENSION IF NOT EXISTS pgcrypto"
sudo -u postgres psql -d artgame_test -c "CREATE EXTENSION IF NOT EXISTS pgcrypto"

echo "Дальше: заполнить /etc/artgame-app/{prod,test}.env по env.example, затем deploy/deploy.sh test"

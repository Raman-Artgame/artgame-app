#!/usr/bin/env bash
# Выкладка одного окружения из распакованной сборки в текущей папке: deploy.sh test|prod
set -euo pipefail
ENV=${1:?test|prod}
SRC=$(cd "$(dirname "$0")/.." && pwd)
DST=/srv/artgame-app/$ENV
rsync -a --delete "$SRC/backend/" "$DST/backend/" --exclude .venv --exclude __pycache__
rsync -a --delete "$SRC/web/" "$DST/web/"
rsync -a --delete "$SRC/deploy/" "$DST/deploy/"
[ -x "$DST/venv/bin/python" ] || python3 -m venv "$DST/venv"
"$DST/venv/bin/pip" install -q -r "$DST/backend/requirements.txt"
chown -R artgame-app:artgame-app "$DST"
install -m 644 "$SRC"/deploy/artgame-*.service "$SRC"/deploy/artgame-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "artgame-api@$ENV" "artgame-constants@$ENV.timer"
systemctl restart "artgame-api@$ENV"
[ "$ENV" = prod ] && systemctl enable --now artgame-backup.timer
sleep 2
PORT=$(grep ^PORT= /etc/artgame-app/$ENV.env | cut -d= -f2)
curl -fsS "http://127.0.0.1:$PORT/api/health"
echo " — $ENV выложен"

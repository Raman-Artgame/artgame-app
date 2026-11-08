#!/usr/bin/env bash
# Одна команда для HEAD: поставить тестовое приложение на test.app.artgame.world.
# Запуск (PowerShell на ПК):
#   ssh -t deploy-admin@109.235.116.40 "curl -fsSL https://raw.githubusercontent.com/Raman-Artgame/artgame-app/<коммит>/app/deploy/install_test.sh -o /tmp/artgame-install.sh && sudo bash /tmp/artgame-install.sh <коммит>"
# Спросит токен бота (только в первый раз) и ключ рабочих мест (один раз; ввод не виден). Остальное делает сам. Prod, шлюз mcp и задачи FIN03/SRC02/DRIVE01 не трогает.
set -euo pipefail
REV=${1:?коммит}
SRC=/srv/artgame-src
HEAD_TG_ID=8172915001   # из листа «Люди» Таблицы «Журнал работ», роль HEAD (не секрет)

echo "== 1/5 код $REV"
if [ ! -d "$SRC/.git" ]; then git clone -q https://github.com/Raman-Artgame/artgame-app "$SRC"; fi
git -C "$SRC" fetch -q origin
git -C "$SRC" checkout -q --detach "$REV"

echo "== 2/5 подготовка сервера"
"$SRC/app/deploy/bootstrap.sh" >/tmp/artgame-bootstrap.log 2>&1 || { tail -30 /tmp/artgame-bootstrap.log; exit 1; }

echo "== 3/5 настройки test"
ENVF=/etc/artgame-app/test.env
if [ ! -f "$ENVF" ]; then
  TOKEN=""
  while [ -z "$TOKEN" ]; do
    read -r -s -p "Вставьте токен бота @artgame_team_bot (из @BotFather) и нажмите Enter: " TOKEN </dev/tty; echo
    if ! curl -fsS "https://api.telegram.org/bot$TOKEN/getMe" | grep -q '"username":"artgame_team_bot"'; then
      echo "Токен не подошёл, ещё раз."; TOKEN=""
    fi
  done
  SA=/etc/artgame-app/google-sa.json
  if [ ! -f "$SA" ]; then
    FOUND=$(grep -rls '"type": *"service_account"' /opt/artgame /etc/artgame /etc/artgame-* 2>/dev/null | grep '\.json$' | head -1 || true)
    if [ -n "$FOUND" ]; then install -m 640 -o root -g artgame-app "$FOUND" "$SA"; echo "сервисный аккаунт: $(grep -o '"client_email": *"[^"]*"' "$SA")"
    else echo "ВНИМАНИЕ: JSON сервисного аккаунта не найден, константы подтянутся позже"; fi
  fi
  OLDMASK=$(umask); umask 027
  cat > "$ENVF" <<ENV
PORT=8101
ARTGAME_ENV_NAME=test
ARTGAME_DATABASE_URL=postgresql:///artgame_test?host=/var/run/postgresql
ARTGAME_BOT_TOKEN=$TOKEN
ARTGAME_HEAD_TG_ID=$HEAD_TG_ID
ARTGAME_PRIVATE_KEY=$(openssl rand -hex 32)
ARTGAME_GOOGLE_SA_FILE=$SA
ENV
  chown root:artgame-app "$ENVF"; chmod 640 "$ENVF"; umask "$OLDMASK"
  unset TOKEN
else
  echo "уже есть, не меняю"
fi
# Адрес страницы для загрузки больших файлов прямо в Google (добавляется один раз)
grep -q '^ARTGAME_PUBLIC_ORIGIN=' "$ENVF" || echo "ARTGAME_PUBLIC_ORIGIN=https://test.app.artgame.world" >> "$ENVF"
# Ключ рабочих мест (страницы из артефактов лежат в репозитории зашифрованными). Спрашивается один раз.
if ! grep -q '^ARTGAME_CONTENT_KEY=' "$ENVF"; then
  KEY=""
  while ! [[ "$KEY" =~ ^[0-9a-f]{64}$ ]]; do
    read -r -s -p "Вставьте ключ рабочих мест (64 символа из треда) и нажмите Enter: " KEY </dev/tty; echo
  done
  echo "ARTGAME_CONTENT_KEY=$KEY" >> "$ENVF"; unset KEY
  echo "ключ рабочих мест записан"
fi

echo "== 4/5 выкладка test"
"$SRC/app/deploy/deploy.sh" test

echo "== 5/5 проверка"
curl -fsS https://test.app.artgame.world/api/health && echo
systemctl start artgame-constants@test.service || true
journalctl -u artgame-constants@test -n 3 --no-pager -o cat || true
curl -s -o /dev/null -w "mcp.artgame.world: %{http_code}\n" https://mcp.artgame.world/
set -a; . "$ENVF"; set +a
# Бот (HEAD 08.11): имя, описание до «Старт», без лишних команд, кнопка меню «ARTGAME» → test.app, ответ на «Старт».
# Сообщение «тест обновлён» HEAD больше не шлём — результат выкладки виден в GitHub Actions.
(cd /srv/artgame-app/test/backend && /srv/artgame-app/test/venv/bin/python -m artgame.tgbot setup) \
  || echo "ВНИМАНИЕ: профиль бота не обновлён (см. выше)"
echo "ГОТОВО: https://test.app.artgame.world"

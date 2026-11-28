#!/usr/bin/env bash
# Разовая настройка автовыкладки на test.app: выполнить ОДИН раз как root на VPS.
#   curl -fsSL https://raw.githubusercontent.com/Raman-Artgame/artgame-app/main/app/deploy/setup_ci_deploy.sh | bash
# Создаёт пользователя artgame-ci, которому по ssh-ключу разрешена ровно одна команда:
# поставить указанный коммит на test (install_test.sh). Ничего другого ключ сделать не может.
# В конце печатает закрытый ключ — его вставить в секрет репозитория TEST_DEPLOY_KEY (GitHub → Settings → Secrets → Actions).
# Повторный запуск безопасен: ключ создаётся заново, старый перестаёт действовать.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "нужен root" >&2; exit 1; }
U=artgame-ci
SRC=/srv/artgame-src
id "$U" >/dev/null 2>&1 || useradd --system --create-home --home-dir /home/$U --shell /bin/bash "$U"
if [ ! -d "$SRC/.git" ]; then git clone -q https://github.com/Raman-Artgame/artgame-app "$SRC"; fi

# Шлюз: выполняется под artgame-ci при входе по ключу, принимает только "deploy <коммит>"
cat > /usr/local/bin/artgame-ci-gate <<'GATE'
#!/usr/bin/env bash
set -euo pipefail
read -r CMD REV _ <<<"${SSH_ORIGINAL_COMMAND:-}"
[ "${CMD:-}" = deploy ] && [[ "${REV:-}" =~ ^[0-9a-f]{7,40}$ ]] || { echo "разрешено только: deploy <коммит>" >&2; exit 2; }
exec sudo -n /usr/local/sbin/artgame-deploy-test "$REV"
GATE
chmod 755 /usr/local/bin/artgame-ci-gate

# Сама выкладка под root: обновить копию репозитория и запустить install_test.sh из него
cat > /usr/local/sbin/artgame-deploy-test <<'DEP'
#!/usr/bin/env bash
set -euo pipefail
REV=${1:?коммит}
[[ "$REV" =~ ^[0-9a-f]{7,40}$ ]] || { echo "плохой коммит" >&2; exit 2; }
SRC=/srv/artgame-src
git -C "$SRC" fetch -q origin
git -C "$SRC" checkout -q --detach "$REV"
exec bash "$SRC/app/deploy/install_test.sh" "$REV" </dev/null
DEP
chmod 755 /usr/local/sbin/artgame-deploy-test

cat > /etc/sudoers.d/artgame-ci <<'SUDO'
artgame-ci ALL=(root) NOPASSWD: /usr/local/sbin/artgame-deploy-test *
SUDO
chmod 440 /etc/sudoers.d/artgame-ci
visudo -cf /etc/sudoers.d/artgame-ci >/dev/null

# Ключ: закрытая часть печатается один раз и на сервере не остаётся
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
ssh-keygen -q -t ed25519 -N '' -C "github-actions test deploy" -f "$T/key"
install -d -m 700 -o "$U" -g "$U" /home/$U/.ssh
printf 'command="/usr/local/bin/artgame-ci-gate",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty %s\n' "$(cat "$T/key.pub")" > /home/$U/.ssh/authorized_keys
chown "$U:$U" /home/$U/.ssh/authorized_keys; chmod 600 /home/$U/.ssh/authorized_keys

echo
echo "================ ГОТОВО ================"
echo "Скопируйте ВСЁ между строками BEGIN и END (включая их) в секрет TEST_DEPLOY_KEY:"
echo "https://github.com/Raman-Artgame/artgame-app/settings/secrets/actions/new"
echo
cat "$T/key"
echo
echo "Отпечаток сервера (не секрет, для сведения): $(ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub)"

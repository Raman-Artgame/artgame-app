# ARTGAME — приложение на своём сервере

- `backend/` — FastAPI + PostgreSQL 16. Вход по подписи Telegram (`X-Telegram-Init-Data`), роли и зоны из базы, журнал действий, константы из листа «Значения» (только «Утверждено» и по «Кто видит»).
- `frontend/` — React + Vite, одна сборка для Telegram Mini App и PWA, тёмный игровой вид.
- `deploy/` — Caddy, службы systemd (`artgame-api@test|prod`, константы каждые 5 мин, ночная копия на Диск), `bootstrap.sh` (однократно), `deploy.sh test|prod`.

Локально: `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt && ARTGAME_TEST_DATABASE_URL=postgresql://… .venv/bin/pytest`.
Секреты только в `/etc/artgame-app/*.env` на сервере (см. `deploy/env.example`).

Сквозной тест экрана: поднять API на пустой базе (`ARTGAME_BOT_TOKEN=123:test-token ARTGAME_HEAD_TG_ID=1000`) через `backend/.venv/bin/python e2e/fake_api.py` (из `backend/`, Диск подменён) и `npx vite preview --port 4173` в `frontend/`, затем `node e2e/smeny.cjs`.

## Рабочие места ролей (из артефактов)

Страницы мест (художники, печать, МОП, калькулятор, дизайн) лежат в `backend/places/<место>/*.enc` — зашифрованы
AES-256-GCM, потому что репозиторий публичный, а внутри ставки и внутренние правила. Ключ `ARTGAME_CONTENT_KEY` — только
в env сервера (install_test.sh спрашивает один раз) и в закрытой папке проекта `app-core/secret/`.
Кто что открывает — `PLACES` в `backend/artgame/places.py`. Обновить место из новой версии артефакта:
скачать файлы артефакта в папку и `ARTGAME_CONTENT_KEY=… python -m artgame.pack_places <папка> <место>` (из `backend/`).
`window.claude` на странице заменяет `place_shim.js`: общая база → таблица `place_docs`, `config/values` → «Значения»
(по аудитории места), скачивание → через сервер (в Telegram — `downloadFile`). ИИ-помощник и Битрикс в местах пока выключены.
Тест: тот же API с ключом, затем `node e2e/places.cjs`, `node e2e/sdelki.cjs`, `node e2e/kabinety.cjs` (кабинеты команды) и `node e2e/prodakshn.cjs` (саппорт, продакшн), `node e2e/oplaty.cjs` (оплата клиента с чеком, сверка HEAD, «Оплаты») (сделки МОП; Битрикс в fake_api подменён ответами из `tests/test_bx.py`).

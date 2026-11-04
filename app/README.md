# ARTGAME — приложение на своём сервере

- `backend/` — FastAPI + PostgreSQL 16. Вход по подписи Telegram (`X-Telegram-Init-Data`), роли и зоны из базы, журнал действий, константы из листа «Значения» (только «Утверждено» и по «Кто видит»).
- `frontend/` — React + Vite, одна сборка для Telegram Mini App и PWA, тёмный игровой вид.
- `deploy/` — Caddy, службы systemd (`artgame-api@test|prod`, константы каждые 5 мин, ночная копия на Диск), `bootstrap.sh` (однократно), `deploy.sh test|prod`.

Локально: `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt && ARTGAME_TEST_DATABASE_URL=postgresql://… .venv/bin/pytest`.
Секреты только в `/etc/artgame-app/*.env` на сервере (см. `deploy/env.example`).

Сквозной тест экрана: поднять API на пустой базе (`ARTGAME_BOT_TOKEN=123:test-token ARTGAME_HEAD_TG_ID=1000`) на :8100 и `npx vite preview --port 4173` в `frontend/`, затем `node e2e/smeny.cjs`.

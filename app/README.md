# ARTGAME — приложение на своём сервере

- `backend/` — FastAPI + PostgreSQL 16. Вход по подписи Telegram (`X-Telegram-Init-Data`), роли и зоны из базы, журнал действий, константы из листа «Значения» (только «Утверждено» и по «Кто видит»).
- `frontend/` — React + Vite, одна сборка для Telegram Mini App и PWA, тёмный игровой вид.
- `deploy/` — Caddy, службы systemd (`artgame-api@test|prod`, константы каждые 5 мин, ночная копия на Диск), `bootstrap.sh` (однократно), `deploy.sh test|prod`.

Локально: `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt && ARTGAME_TEST_DATABASE_URL=postgresql://… .venv/bin/pytest`.
Секреты только в `/etc/artgame-app/*.env` на сервере (см. `deploy/env.example`).

-- Вход с компьютера без Telegram (HEAD 06.11): код приходит от бота в Telegram, браузер получает сессию на 30 дней.
CREATE TABLE IF NOT EXISTS login_codes (
    id          bigserial PRIMARY KEY,
    person_id   bigint NOT NULL REFERENCES people(id),
    code_hash   text NOT NULL,
    expires_at  timestamptz NOT NULL,
    tries       int NOT NULL DEFAULT 0,
    used        boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS login_codes_person ON login_codes (person_id, created_at DESC);
CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash  text PRIMARY KEY,
    person_id   bigint NOT NULL REFERENCES people(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    last_seen   timestamptz NOT NULL DEFAULT now(),
    agent       text
);

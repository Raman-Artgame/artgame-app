-- «Диалог с HEAD» (HEAD 09.11): у каждого сотрудника личный диалог с HEAD; HEAD пишет одному или сразу всем/по ролям.
-- Ничего не удаляется. tg_msg_id — номер уведомления бота у получателя: ответ на него свайпом в Telegram попадает в диалог.
CREATE TABLE IF NOT EXISTS dm_broadcasts (
    id          bigserial PRIMARY KEY,
    author_id   bigint NOT NULL REFERENCES people(id),
    text        text NOT NULL,
    roles       text[],                      -- NULL — всем
    sent        int NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS dm (
    id           bigserial PRIMARY KEY,
    person_id    bigint NOT NULL REFERENCES people(id),   -- чей диалог (сотрудник)
    from_head    boolean NOT NULL,
    author_id    bigint NOT NULL REFERENCES people(id),
    text         text NOT NULL,
    broadcast_id bigint REFERENCES dm_broadcasts(id),
    via          text NOT NULL DEFAULT 'app' CHECK (via IN ('app', 'tg')),
    tg_msg_id    bigint,
    read_at      timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS dm_person ON dm (person_id, created_at DESC);
CREATE INDEX IF NOT EXISTS dm_unread ON dm (from_head, person_id) WHERE read_at IS NULL;
CREATE INDEX IF NOT EXISTS dm_tg ON dm (tg_msg_id) WHERE tg_msg_id IS NOT NULL;

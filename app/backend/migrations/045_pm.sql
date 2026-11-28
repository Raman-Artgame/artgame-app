-- «Чат» как в Telegram (HEAD 11.11: «объявления и вопросы к HEAD — одним; личные переписки — чтобы друг с другом могли общаться»).
-- Личные чаты любой ↔ любой: pm (видят только двое). Прежние личные чаты с HEAD (dm.head_id) копируются сюда; dm не трогаем.
CREATE TABLE IF NOT EXISTS pm (
    id           bigserial PRIMARY KEY,
    sender_id    bigint NOT NULL REFERENCES people(id),
    recipient_id bigint NOT NULL REFERENCES people(id),
    text         text NOT NULL,
    via          text NOT NULL DEFAULT 'app',
    read_at      timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    dm_id        bigint UNIQUE REFERENCES dm(id),        -- откуда скопировано (миграция)
    CHECK (sender_id <> recipient_id)
);
CREATE INDEX IF NOT EXISTS pm_pair ON pm (LEAST(sender_id, recipient_id), GREATEST(sender_id, recipient_id), created_at);
CREATE INDEX IF NOT EXISTS pm_unread ON pm (recipient_id) WHERE read_at IS NULL;
INSERT INTO pm (sender_id, recipient_id, text, via, read_at, created_at, dm_id)
SELECT CASE WHEN from_head THEN author_id ELSE person_id END, CASE WHEN from_head THEN person_id ELSE head_id END,
       text, via, read_at, created_at, id
  FROM dm WHERE broadcast_id IS NULL AND head_id IS NOT NULL
   AND (CASE WHEN from_head THEN author_id ELSE person_id END) <> (CASE WHEN from_head THEN person_id ELSE head_id END)
ON CONFLICT (dm_id) DO NOTHING;

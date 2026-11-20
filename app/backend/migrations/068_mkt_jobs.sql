-- Отдел маркетинга (HEAD 14.11): у каждого своя задача, руководитель (Кристина) видит всё и проверяет первой, потом HEAD.
ALTER TABLE people ADD COLUMN IF NOT EXISTS mkt_job text CHECK (mkt_job IN ('lead', 'smm', 'stories', 'target', 'video'));
ALTER TABLE mkt_posts DROP CONSTRAINT IF EXISTS mkt_posts_status_check;
ALTER TABLE mkt_posts ADD CONSTRAINT mkt_posts_status_check
    CHECK (status IN ('draft', 'check', 'pending', 'approved', 'rejected', 'published', 'cancelled'));
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS checked_by bigint REFERENCES people(id);
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS checked_at timestamptz;
-- Объём в месяц по договору с агентством (Договор №14 от 16.10.2026, п. 1): правит HEAD, в код не вшито.
CREATE TABLE IF NOT EXISTS mkt_norms (
    kind       text PRIMARY KEY CHECK (kind IN ('reels', 'post', 'stories')),
    title      text NOT NULL,
    per_month  integer NOT NULL CHECK (per_month >= 0),
    sort       integer NOT NULL DEFAULT 0,
    updated_by bigint REFERENCES people(id),
    updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO mkt_norms (kind, title, per_month, sort) VALUES ('reels', 'Рилс', 8, 1), ('post', 'Посты', 7, 2), ('stories', 'Сторис', 70, 3)
ON CONFLICT (kind) DO NOTHING;

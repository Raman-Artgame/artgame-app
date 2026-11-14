-- Рабочее место маркетинга (HEAD 14.11): роль «Маркетолог» (СММ, видео, таргет — одна роль, кто есть кто — HEAD в «Команде»),
-- зона «Маркетинг» и контент-план. Каждую публикацию утверждает HEAD: без «Утверждаю» отметить «Опубликовано» нельзя.
INSERT INTO roles (code, title, level) VALUES ('marketer', 'Маркетолог', 3) ON CONFLICT (code) DO NOTHING;
INSERT INTO zones (code, title) VALUES ('marketing', 'Маркетинг') ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS mkt_posts (
    id            bigserial PRIMARY KEY,
    title         text NOT NULL,
    channel       text NOT NULL DEFAULT 'instagram',      -- instagram · tiktok · youtube · 2gis · site · other
    kind          text NOT NULL DEFAULT 'reels',          -- reels · post · carousel · stories
    plan_date     date,
    caption       text,
    file_ids      bigint[] NOT NULL DEFAULT '{}',         -- материал из «Медиа» (files.kind='media')
    object_id     bigint REFERENCES objects(id),          -- про какой проект (необязательно)
    status        text NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft', 'pending', 'approved', 'rejected', 'published', 'cancelled')),
    author_id     bigint NOT NULL REFERENCES people(id),
    submitted_at  timestamptz,
    reviewed_by   bigint REFERENCES people(id),
    reviewed_at   timestamptz,
    review_note   text,
    url           text,                                    -- ссылка на вышедшую публикацию
    published_at  timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mkt_posts_date ON mkt_posts (plan_date);
CREATE INDEX IF NOT EXISTS mkt_posts_status ON mkt_posts (status);

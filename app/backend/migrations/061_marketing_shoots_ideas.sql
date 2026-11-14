-- Маркетинг, шаг 2 (HEAD 14.11): графики съёмок, идеи/сценарии, итог публикации («дала результат» или нет).
CREATE TABLE IF NOT EXISTS mkt_ideas (
    id          bigserial PRIMARY KEY,
    title       text NOT NULL,
    text        text,                                       -- сценарий, раскадровка, задумка
    kind        text NOT NULL DEFAULT 'reels',
    object_id   bigint REFERENCES objects(id),
    status      text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'work', 'done', 'dropped')),
    author_id   bigint NOT NULL REFERENCES people(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mkt_shoots (
    id          bigserial PRIMARY KEY,
    title       text NOT NULL,
    shoot_date  date NOT NULL,
    at_time     text,                                       -- «10:00», «после смены»
    object_id   bigint REFERENCES objects(id),              -- по проекту; NULL — вне проектов (студия, интервью, говорящая голова)
    place       text,
    crew        bigint[] NOT NULL DEFAULT '{}',             -- кто снимает (people.id)
    idea_id     bigint REFERENCES mkt_ideas(id),
    note        text,
    status      text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned', 'done', 'cancelled')),
    author_id   bigint NOT NULL REFERENCES people(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mkt_shoots_date ON mkt_shoots (shoot_date);
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS result text CHECK (result IN ('good', 'weak'));   -- дала результат / нет
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS result_note text;
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS views int;
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS leads int;
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS idea_id bigint REFERENCES mkt_ideas(id);

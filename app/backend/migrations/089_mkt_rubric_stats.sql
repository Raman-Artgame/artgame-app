-- Маркетинг (HEAD 26.11, шаги 5–6): рубрика у публикации, две недостающие нормы договора и недельный вывод агентства.
-- Нормы — только количество в месяц (правит HEAD), без цифр по рубрикам: «пока просто список, свяжем, когда будет маркетолог».
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS rubric_id bigint REFERENCES mkt_rubrics(id);
CREATE INDEX IF NOT EXISTS mkt_posts_rubric ON mkt_posts (rubric_id);
ALTER TABLE mkt_norms DROP CONSTRAINT IF EXISTS mkt_norms_kind_check;
ALTER TABLE mkt_norms ADD CONSTRAINT mkt_norms_kind_check CHECK (kind IN ('reels', 'post', 'stories', 'ad', 'video', 'ig_report'));
INSERT INTO mkt_norms (kind, title, per_month, sort) VALUES ('video', 'Ролики видеографа', 8, 5), ('ig_report', 'Отчёт Instagram (раз в неделю)', 4, 6)
ON CONFLICT (kind) DO NOTHING;
-- Недельный вывод агентства: что сработало и что делаем дальше. Цифры считает приложение, здесь — только слова людей.
CREATE TABLE IF NOT EXISTS mkt_reports (
    id         bigserial PRIMARY KEY,
    week       date NOT NULL UNIQUE,                 -- понедельник недели, о которой отчёт
    worked     text NOT NULL,                        -- что сработало
    next_step  text NOT NULL,                        -- что делаем на следующей неделе
    author_id  bigint NOT NULL REFERENCES people(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

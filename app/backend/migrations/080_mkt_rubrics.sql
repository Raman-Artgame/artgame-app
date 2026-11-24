-- Маркетинг (HEAD 24.11 «делай»): рубрики-метки и поиск в «Медиа», сценарии с утверждением HEAD → «Съёмка» с папкой,
-- исходники агентства прямо в рубрику (без доступа к Диску).
CREATE TABLE IF NOT EXISTS mkt_rubrics (
    id      bigserial PRIMARY KEY,
    title   text NOT NULL UNIQUE,
    project boolean NOT NULL DEFAULT false,     -- метка материала с объектов («До/после»), а не папка «02 КОНТЕНТ»
    sort    integer NOT NULL DEFAULT 100
);
INSERT INTO mkt_rubrics (title, project, sort) VALUES
    ('Процесс росписи', false, 10), ('Печать на стене', false, 20), ('Картины и холсты', false, 30), ('Команда и закулисье', false, 40),
    ('Эксперт', false, 50), ('Обучение', false, 60), ('Стили и идеи', false, 70), ('HR', false, 80), ('Акции, события, коллаборации', false, 90),
    ('До/после', true, 110), ('Отзывы', true, 120), ('Готовые работы', true, 130)
ON CONFLICT (title) DO NOTHING;
CREATE TABLE IF NOT EXISTS file_tags (
    file_id   bigint NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    rubric_id bigint NOT NULL REFERENCES mkt_rubrics(id),
    set_by    bigint REFERENCES people(id),
    set_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (file_id, rubric_id)
);
CREATE INDEX IF NOT EXISTS file_tags_rubric ON file_tags (rubric_id);
ALTER TABLE files DROP CONSTRAINT IF EXISTS files_kind_check;
ALTER TABLE files ADD CONSTRAINT files_kind_check CHECK (kind IN ('photo', 'design', 'receipt', 'doc', 'media', 'pub', 'src'));
ALTER TABLE files ADD COLUMN IF NOT EXISTS src_folder text;     -- исходник: «2026-11-24 Название» внутри «<рубрика>/Исходники»
-- сценарий: автор → «На утверждение» → HEAD → «В съёмку» (дата + папка на Диске со сценарием)
ALTER TABLE mkt_ideas DROP CONSTRAINT IF EXISTS mkt_ideas_status_check;
ALTER TABLE mkt_ideas ADD CONSTRAINT mkt_ideas_status_check CHECK (status IN ('new', 'pending', 'approved', 'rejected', 'work', 'done', 'dropped'));
ALTER TABLE mkt_ideas ADD COLUMN IF NOT EXISTS rubric_id bigint REFERENCES mkt_rubrics(id);
ALTER TABLE mkt_ideas ADD COLUMN IF NOT EXISTS reviewed_by bigint REFERENCES people(id);
ALTER TABLE mkt_ideas ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
ALTER TABLE mkt_ideas ADD COLUMN IF NOT EXISTS review_note text;
ALTER TABLE mkt_shoots ADD COLUMN IF NOT EXISTS rubric_id bigint REFERENCES mkt_rubrics(id);
ALTER TABLE mkt_shoots ADD COLUMN IF NOT EXISTS drive_folder text;   -- id папки исходников этой съёмки
ALTER TABLE mkt_shoots ADD COLUMN IF NOT EXISTS folder_name text;
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS ad_saved text;        -- реклама утверждена: куда легли креативы («Реклама/2026-11») или ошибка

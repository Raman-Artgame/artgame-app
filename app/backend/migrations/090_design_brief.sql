-- HEAD 26.11 «всё окей, давай начинаем»: ТЗ дизайнеру. В задаче на дизайн — срок, старт работ, лёгкий бриф МОП (кнопками),
-- бриф клиента по ссылке (без входа, ответы ложатся в задачу), вопросы дизайнера к МОП, счётчик кругов правок.
-- Материалы к ТЗ (фото стен, развёртки, примеры) — файлы вида brief в папке сделки «ДИЗАЙН / Фото объекта»:
-- это не эскизы, бригада и закрытие считают эскизами только kind='design'.
ALTER TABLE files DROP CONSTRAINT IF EXISTS files_kind_check;
ALTER TABLE files ADD CONSTRAINT files_kind_check CHECK (kind IN ('photo', 'design', 'receipt', 'doc', 'media', 'pub', 'src', 'brief'));

ALTER TABLE design_tasks ADD COLUMN IF NOT EXISTS start_on date;                        -- когда клиент хочет начать работы
ALTER TABLE design_tasks ADD COLUMN IF NOT EXISTS brief jsonb NOT NULL DEFAULT '{}';    -- лёгкий бриф: who, style, mood (списки)
ALTER TABLE design_tasks ADD COLUMN IF NOT EXISTS tz_by bigint REFERENCES people(id);   -- кто последним дополнил ТЗ
ALTER TABLE design_tasks ADD COLUMN IF NOT EXISTS tz_at timestamptz;
ALTER TABLE design_tasks ADD COLUMN IF NOT EXISTS rounds integer NOT NULL DEFAULT 0;    -- круги правок: каждый переход в «Правки»
ALTER TABLE design_tasks ADD COLUMN IF NOT EXISTS brief_token text UNIQUE;              -- ссылка клиенту на бриф
ALTER TABLE design_tasks ADD COLUMN IF NOT EXISTS client_brief jsonb;                   -- ответы клиента
ALTER TABLE design_tasks ADD COLUMN IF NOT EXISTS client_brief_at timestamptz;

CREATE TABLE IF NOT EXISTS design_task_msgs (
  id         bigserial PRIMARY KEY,
  task_id    bigint NOT NULL REFERENCES design_tasks(id),
  person_id  bigint NOT NULL REFERENCES people(id),
  kind       text NOT NULL CHECK (kind IN ('ask', 'answer')),   -- вопрос дизайнера / ответ МОП
  text       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS design_task_msgs_task ON design_task_msgs (task_id, id);

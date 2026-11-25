-- HEAD 25.11 «в целом норм, давай попробуем»: задачи на дизайн при сделке. МОП жмёт «Нужен дизайн» в карточке сделки
-- (любая стадия, сколько угодно раз) — сделка из «Продаж» никуда не уезжает, у дизайнера появляется карточка во вкладке
-- «Дизайн» с его привычными стадиями. Единиц задачи не дают: единица одна за весь проект. В Битрикс ничего не пишем.
CREATE TABLE IF NOT EXISTS design_tasks (
  id          bigserial PRIMARY KEY,
  deal_id     bigint NOT NULL,
  deal_title  text NOT NULL DEFAULT '',
  city        text,
  title       text NOT NULL,                       -- что делаем: «столовая», «спортзал»
  note        text,                                -- задача словами МОП
  stage       text NOT NULL DEFAULT 'new',         -- new | urgent | info | work | wait | fix | mop | done
  designer_id bigint REFERENCES people(id),
  size        text,
  deadline    date,
  link        text,                                -- ссылка на эскиз, если файла нет
  file_id     bigint REFERENCES files(id),         -- эскиз файлом в папке сделки ДИЗАЙН
  status      text NOT NULL DEFAULT 'active',      -- active | cancelled
  created_by  bigint NOT NULL REFERENCES people(id),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  approved_at timestamptz
);
CREATE INDEX IF NOT EXISTS design_tasks_deal ON design_tasks (deal_id);
CREATE INDEX IF NOT EXISTS design_tasks_open ON design_tasks (stage) WHERE status = 'active';

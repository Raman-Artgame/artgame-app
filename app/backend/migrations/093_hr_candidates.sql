-- HEAD 26.11 «отдел HR в приложении»: анкета кандидата по ссылке без входа → «Команда → Кандидаты».
-- Строка кандидата сама дописывается в «БАЗУ КАНДИДАТОВ И ПОДРЯДЧИКОВ» (лист направления), принятый — в «СОТРУДНИКИ И СУППОРТЫ».
CREATE TABLE IF NOT EXISTS candidates (
  id            bigserial PRIMARY KEY,
  token         text UNIQUE NOT NULL,                 -- кандидат дозагружает фото и резюме своей анкеты
  dir           text NOT NULL,                        -- направление: art, print (hr_forms.FORMS)
  full_name     text NOT NULL,
  phone         text NOT NULL,                        -- 87771234567, как в базе кандидатов
  city          text,
  level         text,                                 -- желаемая ступень (код роли)
  answers       jsonb NOT NULL DEFAULT '{}',
  lang          text NOT NULL DEFAULT 'ru',
  source        text,                                 -- метка ссылки (?src=) или ответ «откуда узнал»
  stage         text NOT NULL DEFAULT 'new'
                CHECK (stage IN ('new', 'talk', 'interview', 'trial', 'hired', 'reserve', 'rejected')),
  stars         smallint CHECK (stars BETWEEN 1 AND 5),
  note          text,
  reason        text,                                 -- резерв / отказ: почему
  self_refused  boolean NOT NULL DEFAULT false,       -- отказался сам → в базе «Не актуален», иначе «Не приглашать»
  meet_on       date,                                 -- собеседование
  trial_on      date,                                 -- пробная смена
  trial_object  bigint,                               -- сделка пробной смены
  trial_acc     bigint REFERENCES fin_accruals(id),  -- оплата пробной: только если приняли (HEAD 26.11), начисление в ФОТ при входе
  hired_role    text REFERENCES roles(code),
  hired_at      timestamptz,
  person_id     bigint REFERENCES people(id),         -- вошёл в приложение после «Принять»
  prior         jsonb,                                -- уже был в базе: лист, статус, комментарий, последний контакт
  drive_folder  text,
  sheet_name    text,                                 -- лист базы, куда записан
  sheet_at      timestamptz,                          -- когда строка в базе обновлена
  staff_at      timestamptz,                          -- когда дописан в «Сотрудники и суппорты»
  submitted_at  timestamptz,                          -- кандидат дослал фото и нажал «Готово»
  stage_at      timestamptz NOT NULL DEFAULT now(),
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS candidates_stage ON candidates (stage, created_at DESC);
CREATE INDEX IF NOT EXISTS candidates_phone ON candidates (phone);

CREATE TABLE IF NOT EXISTS candidate_files (
  id         bigserial PRIMARY KEY,
  cand_id    bigint NOT NULL REFERENCES candidates(id),
  kind       text NOT NULL CHECK (kind IN ('photo', 'resume')),
  name       text NOT NULL,
  mime       text NOT NULL,
  size       integer NOT NULL,
  drive_id   text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS candidate_files_cand ON candidate_files (cand_id, id);

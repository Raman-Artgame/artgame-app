-- HEAD 26.11 «сначала со всем ознакомились»: новый сотрудник после «Принять» читает «Правила игры» своей роли, ТБ
-- и принимает соглашение о неразглашении и интеллектуальной собственности. Пока не закончил — смены и расходы закрыты.
ALTER TABLE people ADD COLUMN IF NOT EXISTS onboard_from timestamptz;   -- с какого момента обязан ознакомиться (принят / HEAD отправил)

CREATE TABLE IF NOT EXISTS onboard_acks (
  id         bigserial PRIMARY KEY,
  person_id  bigint NOT NULL REFERENCES people(id),
  doc        text NOT NULL CHECK (doc IN ('duties', 'safety', 'nda')),
  role_code  text,                          -- «Правила игры» какой роли
  version    text NOT NULL,                 -- версия документа, которую человек видел
  sha256     text NOT NULL,                 -- отпечаток текста этой версии
  full_name  text,                          -- как подписался
  phone      text,
  ip         text,
  ua         text,
  at         timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS onboard_acks_one ON onboard_acks (person_id, doc, coalesce(role_code, ''), sha256);

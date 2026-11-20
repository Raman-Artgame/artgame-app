-- Проверка в две ступени (HEAD 11.11): смены младших сначала оценивает куратор (ГИП объекта или старший по зоне) —
-- 1–5 звёзд и комментарий, расходы — «верно / есть вопрос»; утверждает только HEAD. Смены самих кураторов — сразу к HEAD.
-- Куратор не успел за 24 ч — запись уходит к HEAD «без оценки». Статус записи не меняется: оценка — отдельные поля.
ALTER TABLE shifts   ADD COLUMN IF NOT EXISTS cur_by       bigint REFERENCES people(id),
                     ADD COLUMN IF NOT EXISTS cur_at       timestamptz,
                     ADD COLUMN IF NOT EXISTS cur_stars    smallint CHECK (cur_stars BETWEEN 1 AND 5),
                     ADD COLUMN IF NOT EXISTS cur_note     text,
                     ADD COLUMN IF NOT EXISTS submitted_at timestamptz,
                     ADD COLUMN IF NOT EXISTS pay_ym       text,     -- по обращению за закрытый месяц: в ФОТ этого месяца
                     ADD COLUMN IF NOT EXISTS appeal_id    bigint;
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS cur_by       bigint REFERENCES people(id),
                     ADD COLUMN IF NOT EXISTS cur_at       timestamptz,
                     ADD COLUMN IF NOT EXISTS cur_ok       boolean,
                     ADD COLUMN IF NOT EXISTS cur_note     text,
                     ADD COLUMN IF NOT EXISTS submitted_at timestamptz,
                     ADD COLUMN IF NOT EXISTS pay_ym       text,
                     ADD COLUMN IF NOT EXISTS appeal_id    bigint;
-- что уже лежит на проверке — сразу к HEAD, как раньше (24 ч считаются от created_at)
UPDATE shifts   SET submitted_at = created_at WHERE submitted_at IS NULL;
UPDATE expenses SET submitted_at = created_at WHERE submitted_at IS NULL;
ALTER TABLE shifts   ALTER COLUMN submitted_at SET DEFAULT now();
ALTER TABLE expenses ALTER COLUMN submitted_at SET DEFAULT now();

-- Обращение на правку (HEAD 11.11): «ошибся или не внёс вовремя». Сначала куратор, утверждает HEAD.
-- shift_late / expense_late — не внёс; shift_fix / expense_fix — ошибка в своей записи (target_id).
-- data — что предлагает сотрудник, old — как было. Закрытый месяц (раньше текущего) не переоткрываем:
-- разница — строкой ФОТ текущего месяца (pay_ym, pay_delta). Ничего не удаляется.
CREATE TABLE IF NOT EXISTS appeals (
    id          bigserial PRIMARY KEY,
    client_uid  uuid UNIQUE NOT NULL,
    person_id   bigint NOT NULL REFERENCES people(id),
    kind        text NOT NULL CHECK (kind IN ('shift_late', 'expense_late', 'shift_fix', 'expense_fix')),
    target_id   bigint,
    object_id   bigint NOT NULL DEFAULT 0,
    zone_code   text NOT NULL,
    day         date NOT NULL,
    why         text NOT NULL,
    data        jsonb NOT NULL DEFAULT '{}',
    old         jsonb,
    status      text NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted', 'approved', 'rejected', 'cancelled')),
    cur_by      bigint REFERENCES people(id),
    cur_at      timestamptz,
    cur_stars   smallint CHECK (cur_stars BETWEEN 1 AND 5),
    cur_ok      boolean,
    cur_note    text,
    checked_by  bigint REFERENCES people(id),
    checked_at  timestamptz,
    reason      text,
    result_id   bigint,                     -- смена / расход, которые появились или исправлены
    pay_ym      text,
    pay_delta   numeric(14,2),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS appeals_review ON appeals (status) WHERE status = 'submitted';
CREATE INDEX IF NOT EXISTS appeals_person ON appeals (person_id, created_at DESC);

ALTER TABLE fin_accruals DROP CONSTRAINT IF EXISTS fin_accruals_kind_check;
ALTER TABLE fin_accruals ADD CONSTRAINT fin_accruals_kind_check
    CHECK (kind IN ('piece','bonus','topup','salary','mop_pct','mop_bonus','reimburse','manual','design_units','catalog','reels','trip_food','appeal'));

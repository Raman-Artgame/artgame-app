-- Доработки HEAD 08.11 (вечер): проживание в командировке, «Выдано и допуски» в кабинете.

-- Проживание — расход с чеком на объект; тратят Главный, Про и Мастер настенной печати (work.CAT_ROLES).
INSERT INTO expense_categories (code, title, sort, article) VALUES ('lodging', 'Проживание (командировка)', 12, 'project')
    ON CONFLICT (code) DO NOTHING;

-- Что выдано человеку: ключи, одежда, инструмент, доступы (пароли не храним — только «что выдано»), и допуски ТБ.
CREATE TABLE person_items (
    id           bigserial PRIMARY KEY,
    person_id    bigint NOT NULL REFERENCES people(id),
    kind         text NOT NULL CHECK (kind IN ('key', 'clothes', 'tool', 'access', 'permit', 'other')),
    title        text NOT NULL,
    qty          int  NOT NULL DEFAULT 1 CHECK (qty > 0),
    note         text,
    status       text NOT NULL DEFAULT 'issued' CHECK (status IN ('issued', 'returned', 'lost')),
    issued_by    bigint NOT NULL REFERENCES people(id),
    issued_at    timestamptz NOT NULL DEFAULT now(),
    ack_at       timestamptz,              -- человек нажал «Получил»
    closed_by    bigint REFERENCES people(id),
    closed_at    timestamptz
);
CREATE INDEX person_items_person ON person_items (person_id, status);

-- Командировки (HEAD 08.11, вариант «сам по городу + МОП»): город сотрудника ≠ город объекта → командировка;
-- МОП может поправить на объекте (objects.trip: null — авто, true/false — вручную). Дорога — смена по ставке роли,
-- суточные pay.trip_food за каждый день со сменой или дорогой на командировочном объекте.
ALTER TABLE people  ADD COLUMN city text;
ALTER TABLE objects ADD COLUMN trip boolean;
ALTER TABLE shifts
    ADD COLUMN kind text NOT NULL DEFAULT 'work' CHECK (kind IN ('work', 'road')),
    ADD COLUMN trip boolean NOT NULL DEFAULT false;
ALTER TABLE fin_accruals DROP CONSTRAINT IF EXISTS fin_accruals_kind_check;
ALTER TABLE fin_accruals ADD CONSTRAINT fin_accruals_kind_check
    CHECK (kind IN ('piece','bonus','topup','salary','mop_pct','mop_bonus','reimburse','manual','design_units','catalog','reels','trip_food'));

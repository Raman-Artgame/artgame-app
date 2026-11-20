-- Кабинеты команды (HEAD 06–07.11.2026): лестница художников, сбор на объект, дизайн в воронке, каталог референсов.

-- Лестница из констант: Саппорт → Художник → Главный художник → Художник-Про (Про выше Главного).
UPDATE roles SET level = 3 WHERE code = 'lead_artist';
UPDATE roles SET level = 4 WHERE code = 'artist_pro';

-- Новые виды начислений: единицы дизайна сверх нормы и каталог референсов.
ALTER TABLE fin_accruals DROP CONSTRAINT IF EXISTS fin_accruals_kind_check;
ALTER TABLE fin_accruals ADD CONSTRAINT fin_accruals_kind_check
    CHECK (kind IN ('piece','bonus','topup','salary','mop_pct','mop_bonus','reimburse','manual','design_units','catalog'));

-- Сбор на объект: один список на объект и зону. Состав — JSON строк (аэрозоль: номер цвета + шт; фасадная: литры;
-- материалы: количество; оборудование: взял/вернул + состояние; расходники: да/нет). После «Сдать» список закрыт.
CREATE TABLE kit_lists (
    id          bigserial PRIMARY KEY,
    object_id   bigint NOT NULL REFERENCES objects(id),
    zone_code   text NOT NULL CHECK (zone_code IN ('mural','print')),
    items       jsonb NOT NULL DEFAULT '{}'::jsonb,
    status      text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed')),
    created_by  bigint NOT NULL REFERENCES people(id),
    updated_by  bigint REFERENCES people(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    closed_by   bigint REFERENCES people(id),
    closed_at   timestamptz
);
CREATE UNIQUE INDEX kit_lists_object_zone ON kit_lists (object_id, zone_code);

-- Дизайн: круги правок по сделке воронки «Дизайн РК» (каждый переход в «Правки» — новый круг, без доплаты).
CREATE TABLE design_rounds (
    id         bigserial PRIMARY KEY,
    deal_id    bigint NOT NULL,
    round      int NOT NULL,
    person_id  bigint REFERENCES people(id),
    at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (deal_id, round)
);

-- Единицы дизайна: засчитываются, когда сделка дошла до «УТВЕРЖДЕНО» (макет и эскиз утверждены).
-- Если проект в работу не пошёл, HEAD снимает единицу с причиной (status = cancelled).
CREATE TABLE design_units (
    deal_id         bigint PRIMARY KEY,
    title           text,
    person_id       bigint REFERENCES people(id),
    bitrix_user_id  bigint,
    size            text,
    units           numeric(6,2) NOT NULL DEFAULT 0,
    rounds          int NOT NULL DEFAULT 0,
    approved_at     timestamptz NOT NULL,
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled')),
    reason          text,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Размер XS — только в приложении: в поле Битрикса «Сложность дизайна» значения XS нет.
CREATE TABLE design_sizes (
    deal_id     bigint PRIMARY KEY,
    size        text NOT NULL CHECK (size IN ('xs','s','m','l','xl')),
    set_by      bigint REFERENCES people(id),
    set_at      timestamptz NOT NULL DEFAULT now()
);

-- Каталог референсов: дизайнер(ы) → HEAD утверждает → +pay.design.catalog, двоим — пополам.
CREATE TABLE design_catalogs (
    id          bigserial PRIMARY KEY,
    title       text NOT NULL,
    style       text,
    url         text,
    authors     bigint[] NOT NULL,
    status      text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','sent','returned','approved','cancelled')),
    comment     text,
    created_by  bigint NOT NULL REFERENCES people(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    sent_at     timestamptz,
    decided_by  bigint REFERENCES people(id),
    decided_at  timestamptz
);

-- Главный дизайнер — на окладе pay.design.lead.month (вакансия, «Значения» 07.11), не по сменам.
UPDATE fin_payees f SET scheme = 'salary', amount_key = 'pay.design.lead.month'
  FROM people p WHERE p.id = f.person_id AND p.role_code = 'lead_designer' AND f.scheme = 'shifts' AND f.amount IS NULL;

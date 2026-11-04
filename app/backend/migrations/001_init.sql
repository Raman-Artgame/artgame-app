-- ARTGAME: базовая схема. Ничего не удаляем: только status = 'cancelled' / 'archived'.

CREATE TABLE IF NOT EXISTS schema_migrations (
    name        text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

-- Справочник ролей (11 ролей из ARCHITECTURE.md). level — порядок для игры.
CREATE TABLE roles (
    code   text PRIMARY KEY,
    title  text NOT NULL,
    level  int  NOT NULL
);
INSERT INTO roles (code, title, level) VALUES
    ('support',        'Саппорт',                      1),
    ('artist',         'Художник',                     2),
    ('artist_pro',     'Художник Про',                 3),
    ('lead_artist',    'Главный художник',             4),
    ('print_operator', 'Оператор настенного принтера', 2),
    ('print_master',   'Мастер настенной печати',      3),
    ('mop',            'МОП',                          2),
    ('mop_vip',        'VIP МОП',                      3),
    ('lead_designer',  'Главный дизайнер',             4),
    ('designer_asst',  'Помощник дизайнера',           2),
    ('head',           'HEAD',                         9);

CREATE TABLE zones (
    code   text PRIMARY KEY,
    title  text NOT NULL
);
INSERT INTO zones (code, title) VALUES
    ('mural',  'Роспись'),
    ('print',  'Печать'),
    ('design', 'Дизайн'),
    ('sales',  'Продажи');

-- Люди. Регистрация сама по ссылке → status 'pending', роль назначает только HEAD.
CREATE TABLE people (
    id            bigserial PRIMARY KEY,
    tg_id         bigint UNIQUE NOT NULL,
    tg_username   text,
    full_name     text NOT NULL,
    phone         text,
    role_code     text REFERENCES roles(code),
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'active', 'blocked')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE person_zones (
    person_id  bigint NOT NULL REFERENCES people(id),
    zone_code  text   NOT NULL REFERENCES zones(code),
    PRIMARY KEY (person_id, zone_code)
);

-- ИИН и реквизиты: видит только HEAD, хранятся зашифрованными (pgcrypto, ключ в env).
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE person_private (
    person_id   bigint PRIMARY KEY REFERENCES people(id),
    iin_enc     bytea,
    bank_enc    bytea,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Объекты = сделки Битрикса (№ сделки = № объекта = № договора).
CREATE TABLE objects (
    id             bigint PRIMARY KEY,          -- ID сделки Битрикса
    title          text NOT NULL,
    city           text,
    bitrix_stage   text,
    drive_folder   text,
    gip_person_id  bigint REFERENCES people(id),
    status         text NOT NULL DEFAULT 'active'
                   CHECK (status IN ('active', 'done', 'archived')),
    synced_at      timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Смены. Проверка: главный своей зоны / ГИП объекта / HEAD, срок 24 ч.
CREATE TABLE shifts (
    id            bigserial PRIMARY KEY,
    client_uid    uuid UNIQUE NOT NULL,          -- для офлайн-очереди: повтор не создаёт дубль
    person_id     bigint NOT NULL REFERENCES people(id),
    object_id     bigint NOT NULL REFERENCES objects(id),
    zone_code     text   NOT NULL REFERENCES zones(code),
    started_at    timestamptz NOT NULL,
    ended_at      timestamptz,
    area_m2       numeric(10,2),
    complexity    text,
    note          text,
    geo_lat       double precision,
    geo_lon       double precision,
    status        text NOT NULL DEFAULT 'submitted'
                  CHECK (status IN ('submitted', 'approved', 'rejected', 'cancelled')),
    checked_by    bigint REFERENCES people(id),
    checked_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE expenses (
    id            bigserial PRIMARY KEY,
    client_uid    uuid UNIQUE NOT NULL,
    person_id     bigint NOT NULL REFERENCES people(id),
    object_id     bigint NOT NULL REFERENCES objects(id),
    category      text   NOT NULL,
    amount        numeric(12,2) NOT NULL CHECK (amount >= 0),
    paid_by       text   NOT NULL DEFAULT 'own' CHECK (paid_by IN ('own', 'company')),
    receipt_url   text,
    note          text,
    status        text NOT NULL DEFAULT 'submitted'
                  CHECK (status IN ('submitted', 'approved', 'rejected', 'cancelled')),
    payout_status text NOT NULL DEFAULT 'none'
                  CHECK (payout_status IN ('none', 'to_pay', 'paid')),
    checked_by    bigint REFERENCES people(id),
    checked_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Константы: снимки листа «Значения». Таблица главная, здесь только версии.
CREATE TABLE constants_versions (
    id          bigserial PRIMARY KEY,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    checksum    text NOT NULL,
    values      jsonb NOT NULL
);

-- Журнал действий: кто, что, когда.
CREATE TABLE audit_log (
    id         bigserial PRIMARY KEY,
    at         timestamptz NOT NULL DEFAULT now(),
    person_id  bigint REFERENCES people(id),
    action     text NOT NULL,
    entity     text,
    entity_id  text,
    data       jsonb
);
CREATE INDEX audit_log_at ON audit_log (at);

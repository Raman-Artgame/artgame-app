-- Статистика рекламы по объявлениям и подсказки таргетологу «антислив» (HEAD 24.11: «всегда была статистика по всем процессам
-- и рекомендации у таргетолога, чтобы не сливался бюджет»).
CREATE TABLE IF NOT EXISTS mkt_meta_ad_day (
    ad_id         text NOT NULL,
    day           date NOT NULL,
    account       text NOT NULL,
    ad_name       text,
    adset_name    text,
    campaign_id   text,
    campaign_name text,
    spend         numeric(14,2) NOT NULL DEFAULT 0,
    currency      text,
    impressions   bigint NOT NULL DEFAULT 0,
    reach         bigint NOT NULL DEFAULT 0,
    clicks        bigint NOT NULL DEFAULT 0,
    messages      integer NOT NULL DEFAULT 0,   -- начатые переписки (Direct, WhatsApp, Messenger)
    leads         integer NOT NULL DEFAULT 0,   -- лид-формы
    fetched_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (ad_id, day)
);
CREATE INDEX IF NOT EXISTS mkt_meta_ad_day_day ON mkt_meta_ad_day (day);
-- частоту показа по дням складывать нельзя — берём у Meta готовую за 7 дней
CREATE TABLE IF NOT EXISTS mkt_meta_ad7 (
    ad_id      text PRIMARY KEY,
    frequency  numeric(8,2),
    fetched_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mkt_ad_hints (
    id         bigserial PRIMARY KEY,
    rule       text NOT NULL,
    obj_id     text NOT NULL,               -- объявление, кабинет или площадка
    title      text NOT NULL,
    text       text NOT NULL,
    advice     text NOT NULL,
    status     text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'done', 'gone')),   -- gone: прошло само
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    closed_by  bigint REFERENCES people(id),
    closed_at  timestamptz,
    note       text
);
CREATE UNIQUE INDEX IF NOT EXISTS mkt_ad_hints_open ON mkt_ad_hints (rule, obj_id) WHERE status = 'open';

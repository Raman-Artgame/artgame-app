-- «Реклама» (HEAD 14.11, «И ссылка, и МОП»): площадки, расход по месяцам и откуда пришёл каждый лид.
-- Площадка у лида: сама — по фразе из своей ссылки WhatsApp в первом сообщении клиента; или её отмечает МОП в карточке лида.
-- В Битрикс ничего не пишем: источник лида там — способ связи (WhatsApp, звонок), а площадку храним здесь.
CREATE TABLE IF NOT EXISTS mkt_channels (
    id         bigserial PRIMARY KEY,
    title      text NOT NULL UNIQUE,
    phrase     text,                       -- готовая первая фраза в ссылке WhatsApp, по ней лид узнаётся сам
    paid       boolean NOT NULL DEFAULT true,   -- платная площадка: показываем расход и цену заявки
    active     boolean NOT NULL DEFAULT true,
    sort       integer NOT NULL DEFAULT 100,
    created_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO mkt_channels (title, phrase, paid, sort) VALUES
    ('Таргет Instagram', 'Здравствуйте! Увидел вашу рекламу в Instagram.', true, 10),
    ('OLX', 'Здравствуйте! Пишу с OLX.', true, 20),
    ('2ГИС', 'Здравствуйте! Нашёл вас в 2ГИС.', true, 30),
    ('Instagram, профиль', 'Здравствуйте! Пишу из вашего Instagram.', false, 40),
    ('Сайт', 'Здравствуйте! Пишу с сайта artgame.kz.', false, 50),
    ('Сарафан, знакомые', NULL, false, 60),
    ('Повторный клиент', NULL, false, 70)
ON CONFLICT (title) DO NOTHING;
CREATE TABLE IF NOT EXISTS mkt_spend (
    channel_id bigint NOT NULL REFERENCES mkt_channels(id),
    ym         text NOT NULL CHECK (ym ~ '^\d{4}-\d{2}$'),
    amount     numeric(14,2) NOT NULL CHECK (amount >= 0),
    source     text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual', 'meta')),
    note       text,
    updated_by bigint REFERENCES people(id),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (channel_id, ym)
);
CREATE TABLE IF NOT EXISTS lead_origin (
    lead_id    bigint PRIMARY KEY,          -- лид Битрикса
    channel_id bigint NOT NULL REFERENCES mkt_channels(id),
    set_by     bigint REFERENCES people(id),    -- NULL — узнан сам по фразе
    set_at     timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mkt_settings (key text PRIMARY KEY, value text NOT NULL);

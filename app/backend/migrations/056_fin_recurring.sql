-- График постоянных оплат (HEAD 10–12.11.2026): аренда, связь, подписки, сервер, Битрикс, госзакуп.
-- Суммы — из «Значений» через статью (fin_articles.plan_key), здесь только какого числа и как часто.
-- «Оплачено» — строка журнала денег с source_ref 'recurring:<id>:<цикл>' (одна оплата на цикл).

INSERT INTO fin_articles (code, title, kind, plan_key, sort) VALUES
    ('sub_wazzup', 'Подписка Ваззап', 'fixed', 'fin.fixed.wazzup', 45)
ON CONFLICT (code) DO NOTHING;

CREATE TABLE fin_recurring (
    id           serial PRIMARY KEY,
    title        text NOT NULL,
    article_code text NOT NULL REFERENCES fin_articles(code),
    every        text NOT NULL DEFAULT 'month' CHECK (every IN ('month', 'year')),
    day          int  NOT NULL CHECK (day BETWEEN 1 AND 31),
    month        int  CHECK (month BETWEEN 1 AND 12),          -- для «раз в год»
    auto         boolean NOT NULL DEFAULT false,               -- автосписание с карты (подписки): расход пишется сам, без чека
    account_code text NOT NULL DEFAULT 'kaspi' REFERENCES fin_accounts(code),   -- откуда списывается автосписание
    start_date   date NOT NULL DEFAULT current_date,           -- раньше этой даты долгов нет
    active       boolean NOT NULL DEFAULT true,
    sort         int  NOT NULL DEFAULT 0,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CHECK ((every = 'year') = (month IS NOT NULL))
);

-- Дни — от HEAD 12.11. Подписки — автосписание (HEAD 12.11: «у меня подписка же»); сервер пока вручную, автопродление HEAD включит позже — тогда auto в приложении. Gigapixel, Freepik — «не помню», пока 1-е; госзакуп — «в начале года», пока 10 января.
INSERT INTO fin_recurring (title, article_code, every, day, month, start_date, sort, auto) VALUES
    ('Аренда студии, Астана',      'rent_studio',        'month', 1,  NULL, '2026-11-12', 10, false),
    ('Аренда офиса продаж',        'rent_office',        'month', 1,  NULL, '2026-11-12', 11, false),
    ('Аренда магазина',            'rent_shop',          'month', 1,  NULL, '2026-11-12', 12, false),
    ('Баланс телефонии',           'telephony',          'month', 2,  NULL, '2026-11-12', 20, false),
    ('Аренда мастерской, Шымкент', 'rent_workshop_shym', 'month', 8,  NULL, '2026-11-12', 30, false),
    ('Интернет, Астана',           'communication',      'month', 8,  NULL, '2026-11-12', 31, false),
    ('Аренда мастерской, Астана',  'rent_workshop',      'month', 11, NULL, '2026-11-12', 40, false),
    ('Ваззап',                     'sub_wazzup',         'month', 11, NULL, '2026-11-12', 41, true),
    ('ChatGPT',                    'sub_chatgpt',        'month', 11, NULL, '2026-11-12', 42, true),
    ('Claude',                     'sub_claude',         'month', 20, NULL, '2026-11-12', 50, true),
    ('Сервер (хостинг)',           'hosting',            'month', 20, NULL, '2026-11-12', 51, false),
    ('Gigapixel',                  'sub_gigapixel',      'month', 1,  NULL, '2026-11-12', 60, true),
    ('Freepik',                    'sub_freepik',        'month', 1,  NULL, '2026-11-12', 61, true),
    ('Битрикс24, за год',          'bitrix',             'year',  14, 8,    '2026-11-12', 70, false),
    ('Госзакуп, подписка за год',  'tenders',            'year',  10, 1,    '2026-11-12', 71, false);

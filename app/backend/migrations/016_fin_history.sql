-- История 2026 (январь–октябрь) в базе приложения (HEAD 06.11: «объединить все данные за 2026 год в одну таблицу»).
-- Деньги истории — на отдельном счёте «История (до ноября)»: остатки реальных счетов начинаются с ноября с нуля,
-- а годовые итоги прихода/расхода видны целиком.
INSERT INTO fin_accounts (code, title, sort) VALUES ('hist', 'История (до ноября)', 9) ON CONFLICT (code) DO NOTHING;

-- Проекты года — копия листа «Проекты <год>» (единый финучёт), обновляется сервером, руками не правится.
CREATE TABLE fin_projects (
    id          bigserial PRIMARY KEY,
    year        int  NOT NULL,
    row_no      int  NOT NULL,                 -- строка листа: одна сделка может стоять в двух строках
    deal_id     bigint,
    month       int  NOT NULL,
    closed      date,
    title       text NOT NULL DEFAULT '',
    city        text NOT NULL DEFAULT '',
    model       text, category text, service text, source text, ip text,
    revenue     numeric(14,2) NOT NULL DEFAULT 0,
    received    numeric(14,2) NOT NULL DEFAULT 0,
    debt        numeric(14,2) NOT NULL DEFAULT 0,
    synced_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (year, row_no)
);
CREATE INDEX fin_projects_month ON fin_projects (year, month);

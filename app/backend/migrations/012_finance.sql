-- Финансы (HEAD 06.11.2026): с ноября весь доход и расход ведётся в приложении, Google Таблица — витрина.
-- Ничего не удаляется: только status = 'cancelled'. Цифры (ставки, лимиты, план бюджета) — из «Значений».

-- Новая роль: мастер-плотник (подрамники и холсты для картин), постоянно закупает материалы.
INSERT INTO roles (code, title, level) VALUES ('carpenter', 'Мастер-плотник', 3) ON CONFLICT (code) DO NOTHING;

-- Счета, где лежат деньги (HEAD 05.11): Kaspi ИП Яковлев, наличные, переводы HEAD.
CREATE TABLE fin_accounts (
    code    text PRIMARY KEY,
    title   text NOT NULL,
    sort    int  NOT NULL,
    active  boolean NOT NULL DEFAULT true
);
INSERT INTO fin_accounts (code, title, sort) VALUES
    ('kaspi', 'Kaspi ИП Яковлев', 1),
    ('cash',  'Наличные',         2),
    ('head',  'Переводы HEAD',    3);

-- Статьи. kind: income — приход; project — расход на объект; stock — закупка на склад (бюджет);
-- canvas — мастерская холстов (бюджет); sales — отдел продаж; fixed / variable — постоянные и переменные расходы компании;
-- payroll — ФОТ; tax — налоги; opening — остаток на начало; transfer — перевод между своими счетами.
CREATE TABLE fin_articles (
    code    text PRIMARY KEY,
    title   text NOT NULL,
    kind    text NOT NULL CHECK (kind IN ('income','project','stock','canvas','sales','fixed','variable','payroll','tax','opening','transfer')),
    plan_key text,                 -- ключ «Значений» с планом в месяц (fin.fixed.*), если есть
    sort    int  NOT NULL,
    active  boolean NOT NULL DEFAULT true
);
INSERT INTO fin_articles (code, title, kind, plan_key, sort) VALUES
    ('opening',        'Остаток на начало',                 'opening',  NULL, 1),
    ('client_payment', 'Оплата клиента',                    'income',   NULL, 10),
    ('design_prepay',  'Предоплата за дизайн',              'income',   NULL, 11),
    ('other_income',   'Прочий приход',                     'income',   NULL, 12),
    ('refund',         'Возврат клиенту',                   'income',   NULL, 13),
    ('transfer',       'Перевод между своими счетами',      'transfer', NULL, 15),
    ('project',        'Расходы на объект (чеки)',          'project',  NULL, 20),
    ('stock',          'Закупка на склад расходников',      'stock',    NULL, 30),
    ('canvas',         'Мастерская холстов',                'canvas',   NULL, 31),
    ('sales',          'Коммерческие расходы — отдел продаж','sales',   NULL, 32),
    ('rent_studio',    'Аренда студии',                     'fixed',    'fin.fixed.rent_studio', 40),
    ('rent_office',    'Аренда офиса',                      'fixed',    'fin.fixed.rent_office', 41),
    ('rent_workshop',  'Аренда мастерской',                 'fixed',    'fin.fixed.rent_workshop', 42),
    ('services',       'Сервисы и ПО (Битрикс и др.)',      'fixed',    'fin.fixed.services', 43),
    ('communication',  'Связь и интернет',                  'fixed',    'fin.fixed.communication', 44),
    ('ads',            'Реклама',                           'variable', NULL, 50),
    ('equipment',      'Оборудование и инструмент',         'variable', NULL, 51),
    ('bank_fee',       'Комиссия банка / Kaspi',            'variable', NULL, 52),
    ('other_expense',  'Прочие расходы',                    'variable', NULL, 59),
    ('payroll',        'Выплата людям (ФОТ)',               'payroll',  NULL, 60),
    ('tax_ipn',        'ИПН',                               'tax',      NULL, 70),
    ('tax_vat',        'НДС к уплате',                      'tax',      NULL, 71),
    ('tax_other',      'Соцплатежи и прочие налоги',        'tax',      NULL, 72);

-- Категории закупок сотрудников «не на объект»: склад расходников и мастерская холстов (article = kind статьи).
INSERT INTO expense_categories (code, title, sort, article) VALUES
    ('stock_paint',   'Краска и грунт',              31, 'stock'),
    ('stock_tools',   'Кисти, валики, инструмент',   32, 'stock'),
    ('stock_tape',    'Скотч, плёнка, укрывка',      33, 'stock'),
    ('stock_ink',     'Чернила и расходники печати', 34, 'stock'),
    ('stock_other',   'Другое на склад',             35, 'stock'),
    ('canvas_wood',   'Брус и подрамники',           41, 'canvas'),
    ('canvas_cloth',  'Холст и грунт',               42, 'canvas'),
    ('canvas_tools',  'Крепёж и инструмент',         43, 'canvas')
ON CONFLICT (code) DO NOTHING;

-- Кому платим. Все: основной состав, саппорты, печать, МОП, плотник, бухгалтер, SMM, подрядчики.
-- Кто в приложении — person_id (начисление из смен и выручки). Кто нет (бухгалтер, SMM) — заводит HEAD.
-- scheme: shifts — смены × ставка роли; salary — оклад в месяц; mop — оклад + % МОП; manual — HEAD вносит сумму сам.
CREATE TABLE fin_payees (
    id          bigserial PRIMARY KEY,
    person_id   bigint UNIQUE REFERENCES people(id),
    name        text NOT NULL,
    grp         text NOT NULL CHECK (grp IN ('core','support','print','sales','workshop','office','marketing','contractor')),
    scheme      text NOT NULL CHECK (scheme IN ('shifts','salary','mop','manual')),
    amount      numeric(12,2),               -- оклад, если не из «Значений»
    amount_key  text,                        -- ключ оклада в «Значениях» (pay.accountant.month и т.п.)
    pay_rule    text NOT NULL DEFAULT 'month' CHECK (pay_rule IN ('month','weekly')),   -- month: аванс до 15, расчёт до 5
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    note        text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Журнал денег: каждый приход и расход одной строкой по дате денег. Отсюда кэшфлоу и остатки по счетам.
-- source + source_ref не дают задвоить одну и ту же оплату (Битрикс, чек, выплата).
CREATE TABLE fin_ledger (
    id              bigserial PRIMARY KEY,
    client_uid      uuid UNIQUE NOT NULL,
    op_date         date NOT NULL,
    account_code    text NOT NULL REFERENCES fin_accounts(code),
    direction       text NOT NULL CHECK (direction IN ('in','out')),
    amount          numeric(14,2) NOT NULL CHECK (amount > 0),
    article_code    text NOT NULL REFERENCES fin_articles(code),
    period          text NOT NULL,                       -- 'YYYY-MM': к какому месяцу относится (ФОТ за октябрь, аренда за ноябрь)
    deal_id         bigint,                              -- сделка Битрикса, если операция по ней
    payee_id        bigint REFERENCES fin_payees(id),
    expense_id      bigint REFERENCES expenses(id),      -- чек сотрудника, если операция из него
    transfer_id     uuid,                                -- две строки перевода между своими счетами
    note            text,
    receipt_file_id bigint REFERENCES files(id),
    source          text NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','app','bitrix','import')),
    source_ref      text,
    status          text NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled')),
    created_by      bigint REFERENCES people(id),
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX fin_ledger_source ON fin_ledger (source, source_ref) WHERE source_ref IS NOT NULL AND status = 'active';
CREATE INDEX fin_ledger_date ON fin_ledger (op_date);
CREATE INDEX fin_ledger_period ON fin_ledger (period);

-- Начисления ФОТ по месяцу: считаются из смен, чеков, выручки и окладов; выплату отмечает только HEAD.
-- kind: piece — смены × ставка; bonus — бонус печати; topup — доплата до гарантированного минимума; salary — оклад;
-- mop_pct — % МОП; mop_bonus — бонус МОП за план; reimburse — возмещение своих денег по чекам; manual — HEAD вручную.
CREATE TABLE fin_accruals (
    id          bigserial PRIMARY KEY,
    period      text NOT NULL,
    payee_id    bigint NOT NULL REFERENCES fin_payees(id),
    kind        text NOT NULL CHECK (kind IN ('piece','bonus','topup','salary','mop_pct','mop_bonus','reimburse','manual')),
    amount      numeric(14,2) NOT NULL,
    detail      text,
    ref         text,                        -- смены / чек, из которых посчитано
    status      text NOT NULL DEFAULT 'active' CHECK (status IN ('active','cancelled')),
    created_by  bigint REFERENCES people(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX fin_accruals_period ON fin_accruals (period, payee_id) WHERE status = 'active';

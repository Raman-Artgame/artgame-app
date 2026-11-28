-- Поправка констант HEAD 06.11 04:27: оклад «Административная нагрузка» — ключ pay.admin_load.month (не привязан к человеку,
-- кому платить — выбирает HEAD в «Людях»); реклама: таргет ($ в день, план без курса не считаем) и контекст (после запуска).
UPDATE fin_payees SET amount_key = 'pay.admin_load.month' WHERE amount_key = 'pay.chief_artist_admin.month';
INSERT INTO fin_articles (code, title, kind, plan_key, sort) VALUES
    ('ads_target',  'Реклама — таргет',           'variable', NULL, 50),
    ('ads_context', 'Реклама — контекст',         'variable', 'fin.var.ads_context.month', 50)
ON CONFLICT (code) DO NOTHING;

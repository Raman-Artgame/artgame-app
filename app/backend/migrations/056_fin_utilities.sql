-- HEAD 10.11: «оплата мастерской вместе с коммунальными — куда вносить?» Отдельная постоянная статья.
-- Суммы-плана нет (в «Значениях» ключа нет) — статья видна в бюджете по факту трат.
INSERT INTO fin_articles (code, title, kind, plan_key, sort) VALUES ('utilities', 'Коммунальные услуги', 'fixed', NULL, 43)
ON CONFLICT (code) DO NOTHING;

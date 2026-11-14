-- Google Workspace (HEAD 14.11.2026): 30 $ в месяц за 2 пользователей, 27-го, автосписание с карты.
-- Сумма — ключ fin.fixed.sub.gworkspace в «Значениях» (13 600 ₸ = 30 $ × 453,64), здесь только дата.
INSERT INTO fin_articles (code, title, kind, plan_key, sort) VALUES
    ('sub_gworkspace', 'Подписка Google Workspace', 'fixed', 'fin.fixed.sub.gworkspace', 45)
ON CONFLICT (code) DO NOTHING;
INSERT INTO fin_recurring (title, article_code, every, day, month, start_date, sort, auto)
VALUES ('Google Workspace', 'sub_gworkspace', 'month', 27, NULL, '2026-11-14', 43, true);

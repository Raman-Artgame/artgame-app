-- Статьи бюджета по списку HEAD 06.11.2026. Суммы — только в «Значениях» (ключи plan_key), здесь их нет.
-- Ключ с окончанием _year — сумма за год, план месяца = /12 (Битрикс, тендеры).
UPDATE fin_articles SET title = 'Аренда студии Астана', plan_key = 'fin.fixed.rent_studio_ast' WHERE code = 'rent_studio';
UPDATE fin_articles SET title = 'Аренда офиса ОП', plan_key = 'fin.fixed.rent_office_sales' WHERE code = 'rent_office';
UPDATE fin_articles SET title = 'Аренда мастерской Астана', plan_key = 'fin.fixed.rent_workshop_ast' WHERE code = 'rent_workshop';
UPDATE fin_articles SET title = 'Интернет Астана', plan_key = 'fin.fixed.internet_ast' WHERE code = 'communication';
UPDATE fin_articles SET active = false WHERE code = 'services';      -- разбито на отдельные подписки ниже
INSERT INTO fin_articles (code, title, kind, plan_key, sort) VALUES
    ('rent_shop',          'Аренда помещения для магазина', 'fixed',    'fin.fixed.rent_shop', 41),
    ('rent_workshop_shym', 'Аренда мастерской Шымкент',     'fixed',    'fin.fixed.rent_workshop_shym', 42),
    ('telephony',          'Баланс телефонии',              'fixed',    'fin.fixed.telephony', 44),
    ('sub_gigapixel',      'Подписка Gigapixel',            'fixed',    'fin.fixed.sub.gigapixel', 45),
    ('sub_freepik',        'Подписка Freepik',              'fixed',    'fin.fixed.sub.freepik', 45),
    ('sub_chatgpt',        'Подписка ChatGPT',              'fixed',    'fin.fixed.sub.chatgpt', 45),
    ('sub_claude',         'Подписка Claude',               'fixed',    'fin.fixed.sub.claude', 45),
    ('bitrix',             'Битрикс24 (оплата за год)',     'fixed',    'fin.fixed.bitrix_year', 46),
    ('tenders',            'Тендеры — подписка на госзакуп (за год)', 'fixed', 'fin.fixed.tenders_year', 46),
    ('hosting',            'Сервер (хостинг)',              'fixed',    'fin.fixed.hosting', 47),
    ('ads_olx',            'Реклама OLX',                   'variable', 'fin.var.ads_olx', 50)
ON CONFLICT (code) DO NOTHING;

-- Оклады: мастер-плотник и помощник дизайнера — оклад из «Значений» (а не смены).
UPDATE fin_payees f SET scheme = 'salary', amount_key = 'pay.carpenter.month'
  FROM people p WHERE p.id = f.person_id AND p.role_code = 'carpenter' AND f.scheme = 'shifts' AND f.amount_key IS NULL;
UPDATE fin_payees f SET scheme = 'salary', amount_key = 'pay.design_assistant.month'
  FROM people p WHERE p.id = f.person_id AND p.role_code = 'designer_asst' AND f.scheme = 'shifts' AND f.amount_key IS NULL;

-- Кого нет в приложении: бухгалтер и SMM.
INSERT INTO fin_payees (name, grp, scheme, amount_key)
SELECT 'Бухгалтер', 'office', 'salary', 'pay.accountant.month' WHERE NOT EXISTS (SELECT 1 FROM fin_payees WHERE amount_key = 'pay.accountant.month');
INSERT INTO fin_payees (name, grp, scheme, amount_key)
SELECT 'SMM', 'marketing', 'salary', 'pay.smm.month' WHERE NOT EXISTS (SELECT 1 FROM fin_payees WHERE amount_key = 'pay.smm.month');

-- Анна Тарапата: оклад + ставка главного художника за смены (схема shifts + amount_key).
INSERT INTO fin_payees (person_id, name, grp, scheme, amount_key)
SELECT p.id, p.full_name, 'core', 'shifts', 'pay.chief_artist_admin.month' FROM people p
 WHERE p.full_name ILIKE '%тарапат%' AND p.status = 'active'
ON CONFLICT (person_id) DO UPDATE SET amount_key = EXCLUDED.amount_key;

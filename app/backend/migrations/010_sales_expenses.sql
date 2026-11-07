-- Траты отдела продаж (HEAD 05.11): статья «Коммерческие расходы — отдел продаж», не в себестоимость проектов,
-- а в стоимость привлечения клиента. Чек обязателен, месячный лимит МОП — ключ mop.expense.limit_month в «Значениях».
ALTER TABLE expense_categories ADD COLUMN IF NOT EXISTS article text NOT NULL DEFAULT 'project';
INSERT INTO expense_categories (code, title, sort, article) VALUES
    ('sales_office',  'Канцелярия и материалы',     21, 'sales'),
    ('sales_trip',    'Выезды и транспорт',         22, 'sales'),
    ('sales_meet',    'Встречи и представительские', 23, 'sales'),
    ('sales_samples', 'Образцы и презентации',      24, 'sales')
ON CONFLICT (code) DO NOTHING;
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS deal_id bigint;          -- сделка Битрикса, по желанию МОП
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS over_limit boolean NOT NULL DEFAULT false;
INSERT INTO zones (code, title) VALUES ('sales', 'Продажи') ON CONFLICT (code) DO NOTHING;
CREATE INDEX IF NOT EXISTS expenses_deal ON expenses (deal_id) WHERE deal_id IS NOT NULL;

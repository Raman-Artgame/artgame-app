-- «Мастерская» (HEAD 09.11): печать работает без проекта — ТО принтера, ремонт, тест печати, обучение, подготовка.
-- Смена на «Офис / без объекта» (id 0), kind='workshop', что делал — в task. Оплата — как смена по часам, без плана и бонуса.
ALTER TABLE shifts DROP CONSTRAINT IF EXISTS shifts_kind_check;
ALTER TABLE shifts ADD CONSTRAINT shifts_kind_check CHECK (kind IN ('work', 'road', 'workshop'));
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS task text;

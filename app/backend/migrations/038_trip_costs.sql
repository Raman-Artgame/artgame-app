-- HEAD 10.11: командировка — галочка в проекте, и сразу пункты расходов: проживание, дорога, транспорт на месте.
-- Суммы каждый раз разные — вносят ГИП / главные / МОП / HEAD расходом компании на объект. Питание — pay.trip_food (3000/день) само.
INSERT INTO expense_categories (code, title, sort, article) VALUES
    ('trip_road',  'Дорога (билеты, бензин)', 13, 'project'),
    ('trip_local', 'Транспорт на месте',      14, 'project'),
    ('trip_other', 'Прочее в командировке',   15, 'project')
ON CONFLICT (code) DO NOTHING;
-- «пересчитать всех»: командировка смены по текущей отметке объекта (или по городу сотрудника и объекта), смены с 1.11
UPDATE shifts s SET trip = CASE
    WHEN o.trip IS NOT NULL THEN o.trip
    ELSE coalesce(pe.city, '') <> '' AND coalesce(o.city, '') <> ''
         AND lower(trim(split_part(pe.city, '(', 1))) <> lower(trim(split_part(o.city, '(', 1))) END
  FROM objects o, people pe
 WHERE o.id = s.object_id AND pe.id = s.person_id AND s.object_id <> 0 AND s.started_at >= '2026-11-01' AND s.status <> 'cancelled';
-- HEAD 10.11: «иногда платим наличкой». Выплата наличными — без чека, сотрудник подтверждает «Получил» в «Мои выплаты».
ALTER TABLE fin_ledger ADD COLUMN IF NOT EXISTS ack_at timestamptz;

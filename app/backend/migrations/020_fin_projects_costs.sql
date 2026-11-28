-- Расходы проектов из «Проекты 2026» (HEAD 08.11: прибыль за янв–окт без материалов завышена). Оценки старой таблицы,
-- в «Сводку» идут отдельной строкой «Материалы и транспорт (оценка)» только за месяцы до живого учёта.
ALTER TABLE fin_projects ADD COLUMN IF NOT EXISTS materials numeric NOT NULL DEFAULT 0;
ALTER TABLE fin_projects ADD COLUMN IF NOT EXISTS transport numeric NOT NULL DEFAULT 0;
ALTER TABLE fin_projects ADD COLUMN IF NOT EXISTS other numeric NOT NULL DEFAULT 0;

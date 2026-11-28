-- Проекты с ноября 2026 — прямо из Битрикса (HEAD 08.11: «не вижу новых проектов»; ручной лист «Проекты 2026» вёлся до октября).
-- origin: 'sheet' — строка листа (история), 'bitrix' — закрытая сделка (row_no = 1 000 000 + ID сделки).
ALTER TABLE fin_projects ADD COLUMN IF NOT EXISTS origin text NOT NULL DEFAULT 'sheet';

-- Съёмка по проекту (HEAD 14.11): маркетолог предлагает в карточке проекта, ГИП объекта подтверждает или предлагает другую дату.
ALTER TABLE mkt_shoots DROP CONSTRAINT IF EXISTS mkt_shoots_status_check;
ALTER TABLE mkt_shoots ADD CONSTRAINT mkt_shoots_status_check CHECK (status IN ('proposed', 'planned', 'done', 'cancelled'));
ALTER TABLE mkt_shoots ADD COLUMN IF NOT EXISTS confirmed_by bigint REFERENCES people(id);
ALTER TABLE mkt_shoots ADD COLUMN IF NOT EXISTS confirmed_at timestamptz;
ALTER TABLE mkt_shoots ADD COLUMN IF NOT EXISTS alt_date date;      -- ГИП: «другая дата»
ALTER TABLE mkt_shoots ADD COLUMN IF NOT EXISTS alt_note text;

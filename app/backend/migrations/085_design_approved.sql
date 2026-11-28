-- HEAD 26.11 «Эстафета сделки»: утверждённый эскиз — это файл, а не ссылка на папку. Дизайнер жмёт «Утверждено» —
-- файл получает метку «В работу». По ней МОП передаёт в производство, бригада видит эскиз первым, закрытие засчитывает дизайн.
ALTER TABLE files ADD COLUMN IF NOT EXISTS approved_at timestamptz;
ALTER TABLE files ADD COLUMN IF NOT EXISTS approved_by bigint REFERENCES people(id);
CREATE INDEX IF NOT EXISTS files_design_approved ON files (object_id) WHERE kind = 'design' AND approved_at IS NOT NULL;

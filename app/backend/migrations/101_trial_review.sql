-- HEAD 28.11: пробный день кандидата идёт под руководством куратора ГИП объекта — он оценивает: звёзды, обязательные
-- пункты (да / частично / нет), итог «брать / под вопросом / не брать» и подробный комментарий. Решение — у HEAD.
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS trial_by          bigint REFERENCES people(id);   -- кто оценивает пробный день
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS trial_review      jsonb;                          -- {items:{key:yes|part|no}, comment}
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS trial_stars       smallint CHECK (trial_stars BETWEEN 1 AND 5);
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS trial_verdict     text CHECK (trial_verdict IN ('take', 'maybe', 'no'));
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS trial_reviewed_at timestamptz;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS trial_reviewed_by bigint REFERENCES people(id);
CREATE INDEX IF NOT EXISTS candidates_trial_by ON candidates (trial_by) WHERE trial_reviewed_at IS NULL;

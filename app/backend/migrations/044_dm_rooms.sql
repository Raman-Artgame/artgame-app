-- «Чат» с подгруппами (HEAD 11.11): личный чат сотрудника с КАЖДЫМ HEAD отдельно + «Руководство» (видят все HEAD) + «Объявления».
-- head_id — с каким HEAD личный чат; NULL у не-рассылки — «Руководство». Прежние диалоги (до 11.11) — личные с первым HEAD (владелец).
ALTER TABLE dm ADD COLUMN IF NOT EXISTS head_id bigint REFERENCES people(id);
UPDATE dm SET head_id = CASE WHEN from_head THEN author_id
                             ELSE (SELECT id FROM people WHERE role_code='head' ORDER BY id LIMIT 1) END
 WHERE broadcast_id IS NULL AND head_id IS NULL;
CREATE INDEX IF NOT EXISTS dm_room ON dm (person_id, head_id, created_at);

-- HEAD 16.11 «проанализировать все блоки под рост нагрузки»: индексы под частые запросы, которые сейчас идут перебором.
-- Ничего не меняет в данных; при сотне строк разницы не видно, при десятках тысяч смен/фото/записей журнала — секунды.
CREATE INDEX IF NOT EXISTS shifts_object ON shifts (object_id, started_at DESC);           -- карточка проекта, «сделано», план на сегодня
CREATE INDEX IF NOT EXISTS shifts_photo_before ON shifts (photo_before) WHERE photo_before IS NOT NULL;   -- галерея: фото отменённой смены
CREATE INDEX IF NOT EXISTS shifts_photo_after ON shifts (photo_after) WHERE photo_after IS NOT NULL;
CREATE INDEX IF NOT EXISTS shift_photos_file ON shift_photos (file_id);
CREATE INDEX IF NOT EXISTS expenses_object ON expenses (object_id, created_at DESC);       -- расходы проекта
CREATE INDEX IF NOT EXISTS audit_log_person ON audit_log (person_id, at DESC);            -- «Журнал», лента Пульта
CREATE INDEX IF NOT EXISTS audit_log_entity ON audit_log (entity, entity_id);
CREATE INDEX IF NOT EXISTS proj_msg_author ON proj_msg (author_id);

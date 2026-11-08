-- Живая карточка объекта (HEAD 08.11 «Что предстоит» — автоматически и интерактивно).
-- Сложность, если МОП её не указал: оценка по сумме сделки и площади против прайса «Значений» (сумму в базе не храним).
ALTER TABLE objects
    ADD COLUMN level_guess      text,
    ADD COLUMN geo              text,            -- «широта;долгота» из адреса сделки — кнопка карты
    ADD COLUMN design_synced_at timestamptz;     -- эскизы из папки сделки «ДИЗАЙН» на Диске
-- Этап, который закрыла смена (грунт → перенос → роспись → детали → лак → сдача).
ALTER TABLE shifts ADD COLUMN stage text;
CREATE INDEX files_drive_id ON files (drive_id) WHERE drive_id IS NOT NULL;

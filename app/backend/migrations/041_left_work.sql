-- HEAD 10.11: сделку по ошибке перенесли с «Выполнение проекта» — ребята не успели внести смены и траты задним числом.
-- left_work_at — когда объект ушёл с «Выполнения»; «Прошлая смена» показывает и такие объекты, пока открыт срок задним числом.
ALTER TABLE objects ADD COLUMN IF NOT EXISTS left_work_at timestamptz;
-- 1579 «Детская площадка» и 1611 «Уйдомдонер» перенесены в «Успешно» 10.11; плюс сданные объекты, где с 1.11 уже были смены
UPDATE objects SET left_work_at = now()
 WHERE left_work_at IS NULL AND id <> 0 AND coalesce(bitrix_stage, '') <> 'UC_AV00QK'
   AND (id IN (1579, 1611) OR id IN (SELECT DISTINCT object_id FROM shifts WHERE started_at >= '2026-11-01'));

-- Правки HEAD 08.11 по рабочим местам: смена по шагам, условия объекта из сделки, «Продакшн», докупка на объект.

-- Смена по шагам: «Начать» (фото стены до) → смена открыта → «Закончить» (фото после, м², что сделал) → на проверку.
ALTER TABLE shifts DROP CONSTRAINT IF EXISTS shifts_status_check;
ALTER TABLE shifts ADD CONSTRAINT shifts_status_check CHECK (status IN ('open', 'submitted', 'approved', 'rejected', 'cancelled'));
ALTER TABLE shifts
    ADD COLUMN work_done    text,
    ADD COLUMN photo_before bigint REFERENCES files(id),
    ADD COLUMN photo_after  bigint REFERENCES files(id);
CREATE INDEX shifts_open ON shifts (person_id) WHERE status = 'open';

-- Условия объекта из сделки (заполняет МОП): сложность, площадь, адрес. Высота/улица/поверхность — из расчёта (deal_calc).
ALTER TABLE objects
    ADD COLUMN level   text,
    ADD COLUMN area_m2 numeric(10,2),
    ADD COLUMN address text;

-- «Продакшн»: материал с объекта (фото, видео, рилс) → МЕДИА / Отчёты; после «утверждаю» HEAD копия в МЕДИА / Продакшн.
ALTER TABLE files DROP CONSTRAINT IF EXISTS files_kind_check;
ALTER TABLE files ADD CONSTRAINT files_kind_check CHECK (kind IN ('photo', 'design', 'receipt', 'doc', 'media'));
ALTER TABLE files
    ADD COLUMN media_type    text CHECK (media_type IN ('photo', 'video', 'reels')),
    ADD COLUMN review        text CHECK (review IN ('pending', 'approved', 'rejected')),
    ADD COLUMN reviewed_by   bigint REFERENCES people(id),
    ADD COLUMN reviewed_at   timestamptz,
    ADD COLUMN review_note   text,
    ADD COLUMN prod_drive_id text;
CREATE INDEX files_media_review ON files (review) WHERE kind = 'media';

-- Рилс после утверждения HEAD — в ФОТ месяца: pay.reels за штуку, не больше pay.reels.max в месяц («Значения»).
ALTER TABLE fin_accruals DROP CONSTRAINT IF EXISTS fin_accruals_kind_check;
ALTER TABLE fin_accruals ADD CONSTRAINT fin_accruals_kind_check
    CHECK (kind IN ('piece','bonus','topup','salary','mop_pct','mop_bonus','reimburse','manual','design_units','catalog','reels'));

-- Саппорт тратит только на такси и докупку на объект.
INSERT INTO expense_categories (code, title, sort, article) VALUES ('purchase', 'Докупка на объект', 11, 'project')
    ON CONFLICT (code) DO NOTHING;

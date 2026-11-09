-- Отчёт задним числом (HEAD 09.11): сколько угодно фото к смене — грузятся по одному после создания смены.
CREATE TABLE IF NOT EXISTS shift_photos (
    id         bigserial PRIMARY KEY,
    shift_id   bigint NOT NULL REFERENCES shifts(id),
    file_id    bigint NOT NULL REFERENCES files(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (shift_id, file_id)
);
CREATE INDEX IF NOT EXISTS shift_photos_shift ON shift_photos (shift_id);

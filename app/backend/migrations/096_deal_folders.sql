-- HEAD 27.11 «чтобы таких эксцессов больше не возникало»: сторож папок. По каждой открытой сделке обеих воронок
-- приложение знает, есть ли папка на Диске, и если создать не вышло или «Объект» пуст — HEAD и МОП видят это сразу.
CREATE TABLE IF NOT EXISTS deal_folders (
    deal_id    bigint PRIMARY KEY,
    title      text NOT NULL DEFAULT '',
    mop_bx_id  bigint,                       -- ответственный в Битриксе: чья строка в «Сегодня»
    folder_id  text,
    state      text NOT NULL CHECK (state IN ('ok', 'error')),
    error      text,
    no_object  boolean NOT NULL DEFAULT false,
    made_by_app boolean NOT NULL DEFAULT false,
    checked_at timestamptz NOT NULL DEFAULT now()
);

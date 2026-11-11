-- «Мой путь» на сервере (HEAD 11.11: «хранить галочки на сервере, чтобы наставник подтверждал пункты, а ты видел прогресс каждого»).
-- Одна строка — пункт чек-листа пути (path — код роли, от которой путь: artist → Главный и т. д.; idx — номер пункта).
-- Сотрудник ставит «есть» (marked_at), наставник подтверждает (confirmed_*) или возвращает с комментарием (returned_*).
-- Ничего не удаляется: снять отметку — marked_at = NULL.
CREATE TABLE IF NOT EXISTS grow_marks (
    person_id    bigint NOT NULL REFERENCES people(id),
    path         text NOT NULL,
    idx          int NOT NULL CHECK (idx >= 0 AND idx < 100),
    marked_at    timestamptz,
    confirmed_by bigint REFERENCES people(id),
    confirmed_at timestamptz,
    returned_by  bigint REFERENCES people(id),
    returned_at  timestamptz,
    note         text,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (person_id, path, idx)
);
CREATE INDEX IF NOT EXISTS grow_marks_wait ON grow_marks (path) WHERE marked_at IS NOT NULL AND confirmed_at IS NULL;

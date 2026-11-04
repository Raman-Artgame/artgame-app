-- Файлы объектов: только через приложение. Хранятся на Google Диске, в базе — карточка файла.
ALTER TABLE objects ADD COLUMN folders jsonb NOT NULL DEFAULT '{}';   -- {"photo": id, "design": id, "receipt": id, "doc": id}
ALTER TABLE objects ADD COLUMN bitrix_category int;

CREATE TABLE files (
    id           bigserial PRIMARY KEY,
    client_uid   uuid UNIQUE NOT NULL,
    object_id    bigint NOT NULL REFERENCES objects(id),
    kind         text NOT NULL CHECK (kind IN ('photo', 'design', 'receipt', 'doc')),
    name         text NOT NULL,
    mime         text,
    size         bigint,
    drive_id     text,                       -- пусто, пока большой файл грузится прямо в Google
    note         text,
    status       text NOT NULL DEFAULT 'ready' CHECK (status IN ('uploading', 'ready', 'archived')),
    uploaded_by  bigint NOT NULL REFERENCES people(id),
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX files_object ON files (object_id, kind, created_at DESC);

ALTER TABLE expenses ADD COLUMN receipt_file_id bigint REFERENCES files(id);

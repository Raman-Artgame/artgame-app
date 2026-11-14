-- Чат проекта (HEAD «да» 13.11): создаётся сам, когда сделка на «Выполнении проекта».
-- Участники считаются на лету: назначенные на объект (object_crew), ГИП объекта, МОП сделки (ответственный в Битриксе), все HEAD.
-- Сняли с объекта — выпал из чата. После «Выполнения»/закрытия чат только для чтения. Бот молчит.
ALTER TABLE objects ADD COLUMN IF NOT EXISTS mop_bx_id int;   -- ответственный по сделке (ASSIGNED_BY_ID), обновляет синхронизация
CREATE TABLE IF NOT EXISTS proj_msg (
    id          bigserial PRIMARY KEY,
    object_id   bigint NOT NULL REFERENCES objects(id),
    author_id   bigint NOT NULL REFERENCES people(id),
    text        text,
    file_id     bigint REFERENCES files(id),               -- фото: лежит в папке сделки (МЕДИА / Отчёты)
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (text IS NOT NULL OR file_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS proj_msg_obj ON proj_msg (object_id, created_at);
CREATE TABLE IF NOT EXISTS proj_read (
    object_id  bigint NOT NULL REFERENCES objects(id),
    person_id  bigint NOT NULL REFERENCES people(id),
    last_id    bigint NOT NULL DEFAULT 0,                  -- последнее прочитанное сообщение
    PRIMARY KEY (object_id, person_id)
);

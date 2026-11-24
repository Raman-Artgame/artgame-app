-- HEAD 24.11: «в чаты нужно добавить функцию прикрепления файлов и фото».
-- Вложения чатов «HEAD», личных и чата проекта (кроме фото проекта — оно, как раньше, в папке сделки) лежат в базе:
-- у робота Диска нет папки для личной переписки, а личный чат видят только двое. До 20 МБ на файл.
CREATE TABLE IF NOT EXISTS chat_files (
    id          bigserial PRIMARY KEY,
    client_uid  uuid UNIQUE NOT NULL,
    name        text NOT NULL,
    mime        text NOT NULL,
    size        integer NOT NULL,
    data        bytea NOT NULL,
    thumb       bytea,                                   -- уменьшенная картинка (jpeg) для ленты; у не-картинок пусто
    uploaded_by bigint NOT NULL REFERENCES people(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE chat_files ALTER COLUMN data SET STORAGE EXTERNAL;   -- не пережимать: фото и архивы уже сжаты
ALTER TABLE dm ADD COLUMN IF NOT EXISTS att_id bigint REFERENCES chat_files(id);
ALTER TABLE pm ADD COLUMN IF NOT EXISTS att_id bigint REFERENCES chat_files(id);
ALTER TABLE proj_msg ADD COLUMN IF NOT EXISTS att_id bigint REFERENCES chat_files(id);
ALTER TABLE proj_msg DROP CONSTRAINT IF EXISTS proj_msg_check;
ALTER TABLE proj_msg ADD CONSTRAINT proj_msg_check CHECK (text IS NOT NULL OR file_id IS NOT NULL OR att_id IS NOT NULL);

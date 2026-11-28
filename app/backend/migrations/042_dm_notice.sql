-- «Диалог с HEAD» (HEAD 10.11): одно уведомление в боте на человека — «Новое сообщение» со счётчиком; после прочтения бот его удаляет.
CREATE TABLE IF NOT EXISTS dm_notice (
    person_id  bigint PRIMARY KEY REFERENCES people(id),   -- кому (сотрудник или HEAD)
    tg_id      bigint NOT NULL,
    msg_id     bigint NOT NULL,
    n          int NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

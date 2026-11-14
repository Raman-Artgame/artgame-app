-- Команда объекта (HEAD 09.11: «Где главный художник назначает на объект?»): кого ГИП / главные / HEAD / МОП поставили на объект.
-- Назначенный получает сообщение бота, объект у него первым в «Смене». Снятие — удаление строки (история — в audit).
CREATE TABLE IF NOT EXISTS object_crew (
    object_id  bigint NOT NULL REFERENCES objects(id),
    person_id  bigint NOT NULL REFERENCES people(id),
    added_by   bigint REFERENCES people(id),
    added_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (object_id, person_id)
);
CREATE INDEX IF NOT EXISTS object_crew_person ON object_crew (person_id);

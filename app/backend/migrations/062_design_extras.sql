-- HEAD 14.11: «главный дизайнер ставит сложность своих проектов; многие уходят сразу в выполнение, нужны правки и докидка онлайн».
-- Дизайн по проекту (сделка основной воронки, objects.id) на любой стадии: сам дизайн проекта или правка/докидка на объекте.
-- Главный дизайнер (или HEAD) вносит → HEAD утверждает → единицы дизайнеру в месяце утверждения (design.unit.<размер>).
CREATE TABLE IF NOT EXISTS design_extras (
    id          bigserial PRIMARY KEY,
    object_id   bigint NOT NULL REFERENCES objects(id),
    person_id   bigint NOT NULL REFERENCES people(id),          -- кто делал (дизайнер)
    kind        text NOT NULL CHECK (kind IN ('design','fix')),  -- дизайн проекта / правка или докидка
    size        text NOT NULL CHECK (size IN ('xs','s','m','l','xl')),
    units       numeric(6,2) NOT NULL DEFAULT 0,
    note        text NOT NULL,
    url         text,
    status      text NOT NULL DEFAULT 'sent' CHECK (status IN ('sent','approved','returned','cancelled')),
    created_by  bigint NOT NULL REFERENCES people(id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    decided_by  bigint REFERENCES people(id),
    decided_at  timestamptz,
    reason      text
);
CREATE INDEX IF NOT EXISTS design_extras_obj ON design_extras (object_id);
CREATE INDEX IF NOT EXISTS design_extras_month ON design_extras (decided_at) WHERE status = 'approved';

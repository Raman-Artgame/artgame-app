-- Рабочие места (бывшие артефакты): их общая база — доска проектов дизайна, VIP-курс и т.п.
-- Ничего не удаляем: запись перезаписывается, история — в audit_log.
CREATE TABLE place_docs (
    place       text   NOT NULL,           -- art | print | mop | dz | calc
    coll        text   NOT NULL,           -- коллекция: projects, vip …
    doc_id      text   NOT NULL,
    data        jsonb  NOT NULL,
    version     int    NOT NULL DEFAULT 1,
    updated_by  bigint REFERENCES people(id),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (place, coll, doc_id)
);

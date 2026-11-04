-- Смены и расходы: справочник категорий (как в прототипе), объект «Офис», причина отказа.
CREATE TABLE expense_categories (
    code    text PRIMARY KEY,
    title   text NOT NULL,
    sort    int  NOT NULL,
    active  boolean NOT NULL DEFAULT true
);
INSERT INTO expense_categories (code, title, sort) VALUES
    ('paint',    'Краска', 1),
    ('brushes',  'Кисти и валики', 2),
    ('varnish',  'Лак', 3),
    ('tape',     'Малярный скотч и плёнка', 4),
    ('primer',   'Грунт', 5),
    ('solvent',  'Растворитель', 6),
    ('ink',      'Чернила / расходники принтера', 7),
    ('transport','Такси / доставка', 8),
    ('rent',     'Аренда (вышка, леса)', 9),
    ('other',    'Другое', 10);

ALTER TABLE expenses ADD CONSTRAINT expenses_category_fk FOREIGN KEY (category) REFERENCES expense_categories(code);
ALTER TABLE expenses ADD COLUMN zone_code text REFERENCES zones(code);
ALTER TABLE shifts   ADD COLUMN reason text;
ALTER TABLE expenses ADD COLUMN reason text;

-- Объект 0 — «Офис / без объекта» (не сделка Битрикса).
INSERT INTO objects (id, title, city) VALUES (0, 'Офис / без объекта', NULL);

CREATE INDEX shifts_person   ON shifts (person_id, started_at DESC);
CREATE INDEX expenses_person ON expenses (person_id, created_at DESC);
CREATE INDEX shifts_review   ON shifts (status) WHERE status = 'submitted';
CREATE INDEX expenses_review ON expenses (status) WHERE status = 'submitted';

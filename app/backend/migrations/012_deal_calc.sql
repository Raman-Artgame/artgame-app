-- Объединённый расчёт карточки сделки (HEAD 06.11): цена + срок и состав. Из него собираются КП и договор.
CREATE TABLE IF NOT EXISTS deal_calc (
    deal_id     bigint PRIMARY KEY,
    data        jsonb NOT NULL,
    person_id   bigint REFERENCES people(id),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- HEAD 22.11 «да давай делаем»: «Ждём клиента» в воронке «Дизайн РК». Сделка уходит из «Горит» в отдельный блок,
-- просрочка не копится; через 7 дней МОП сделки — одно напоминание; «Клиент ответил» — назад в работу, срок сдвигается
-- на дни ожидания. Новой стадии в Битриксе нет — всё хранится здесь.
CREATE TABLE IF NOT EXISTS design_wait (
  id          bigserial PRIMARY KEY,
  deal_id     bigint NOT NULL,
  title       text,
  mop_bx      bigint,                      -- ответственный сделки в Битриксе (МОП) — кому напоминание
  reason      text NOT NULL,
  started_at  timestamptz NOT NULL DEFAULT now(),
  started_by  bigint REFERENCES people(id),
  ended_at    timestamptz,
  ended_by    bigint REFERENCES people(id),
  reminded_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS design_wait_open ON design_wait (deal_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS design_wait_deal ON design_wait (deal_id);

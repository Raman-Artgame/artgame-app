-- HEAD 26.11 «кто что заполняет»: «Клиент согласовал КП» закрепляет сумму и нормы. Новая цена — только после «Снять согласование»
-- (с причиной, остаётся в истории). Одна действующая отметка на сделку; снятые остаются строками.
CREATE TABLE IF NOT EXISTS kp_agreed (
  id          bigserial PRIMARY KEY,
  deal_id     bigint NOT NULL,
  total       numeric NOT NULL,
  data        jsonb NOT NULL DEFAULT '{}',
  agreed_by   bigint NOT NULL REFERENCES people(id),
  agreed_at   timestamptz NOT NULL DEFAULT now(),
  undone_by   bigint REFERENCES people(id),
  undone_at   timestamptz,
  undo_reason text
);
CREATE UNIQUE INDEX IF NOT EXISTS kp_agreed_one ON kp_agreed (deal_id) WHERE undone_at IS NULL;

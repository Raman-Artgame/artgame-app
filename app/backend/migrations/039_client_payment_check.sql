-- HEAD 10.11: оплату клиента вносит МОП в приложении с фото чека («Внести оплату» в сделке), HEAD сверяет: ✓ или ✕.
-- Пока HEAD не сверил — оплата «на сверке» (source = 'app', checked_at пусто). ✕ — обычная отмена строки журнала.
-- Строки, внесённые HEAD или пришедшие из Битрикса, сверять не нужно — у них checked_at остаётся пустым и это не «на сверке».
ALTER TABLE fin_ledger ADD COLUMN IF NOT EXISTS checked_at timestamptz;
ALTER TABLE fin_ledger ADD COLUMN IF NOT EXISTS checked_by bigint REFERENCES people(id);
CREATE INDEX IF NOT EXISTS fin_ledger_unchecked ON fin_ledger (created_at)
    WHERE source = 'app' AND status = 'active' AND checked_at IS NULL AND article_code IN ('client_payment', 'design_prepay');
CREATE INDEX IF NOT EXISTS fin_ledger_deal ON fin_ledger (deal_id) WHERE deal_id IS NOT NULL;

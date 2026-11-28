-- Рекламный кабинет Meta ведётся в долларах (диагностика 25.11): расход переводим в тенге по курсу из «Значений» (mkt.usd_rate),
-- исходную сумму и валюту храним рядом.
ALTER TABLE mkt_meta_day ADD COLUMN IF NOT EXISTS spend_src numeric(14,2);
ALTER TABLE mkt_meta_day ADD COLUMN IF NOT EXISTS currency_src text;
ALTER TABLE mkt_meta_ad_day ADD COLUMN IF NOT EXISTS spend_src numeric(14,2);
ALTER TABLE mkt_meta_ad_day ADD COLUMN IF NOT EXISTS currency_src text;

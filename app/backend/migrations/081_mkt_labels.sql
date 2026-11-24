-- Метки рекламы (HEAD 24.11): у каждой кампании своя фраза для WhatsApp и своя ссылка на сайт — заявка сама получает
-- и площадку, и кампанию.
CREATE TABLE IF NOT EXISTS mkt_labels (
    id         bigserial PRIMARY KEY,
    channel_id bigint NOT NULL REFERENCES mkt_channels(id),
    title      text NOT NULL,                  -- как таргетолог называет кампанию
    active     boolean NOT NULL DEFAULT true,
    created_by bigint REFERENCES people(id),
    created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE lead_origin ADD COLUMN IF NOT EXISTS label_id bigint REFERENCES mkt_labels(id);

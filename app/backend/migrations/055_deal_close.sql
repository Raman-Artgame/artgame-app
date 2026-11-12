-- Закрытие сделки через HEAD (HEAD 12.11 «Да, по рекомендациям», документ «Закрытие сделки через HEAD»).
-- МОП со стадии «Оплата+закрывающие документы» отправляет сделку «На закрытие» (когда все 11 пунктов выполнены),
-- HEAD видит паспорт сделки и жмёт «Закрыть» (приложение переводит сделку в «Оплата получена») или «Вернуть» с причиной.
-- Паспорт хранится здесь навсегда (снимок на момент закрытия), PDF — в папке сделки «ДОКУМЕНТЫ». Ничего не удаляется.
CREATE TABLE IF NOT EXISTS deal_close (
    id           bigserial PRIMARY KEY,
    deal_id      bigint NOT NULL,
    status       text NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'returned', 'closed', 'cancelled')),
    via          text NOT NULL DEFAULT 'app' CHECK (via IN ('app', 'bitrix')),   -- bitrix: сделку перетащили в «Оплата получена» мимо HEAD
    title        text,
    amount       numeric(14, 2),
    sent_by      bigint REFERENCES people(id),
    sent_at      timestamptz NOT NULL DEFAULT now(),
    decided_by   bigint REFERENCES people(id),
    decided_at   timestamptz,
    reason       text,
    points       jsonb NOT NULL DEFAULT '[]',
    passport     jsonb,
    pdf_drive_id text,
    pdf_error    text,
    bx           text
);
CREATE UNIQUE INDEX IF NOT EXISTS deal_close_sent ON deal_close (deal_id) WHERE status = 'sent';
CREATE UNIQUE INDEX IF NOT EXISTS deal_close_closed ON deal_close (deal_id) WHERE status = 'closed';
CREATE INDEX IF NOT EXISTS deal_close_deal ON deal_close (deal_id, id DESC);

-- Сделка закрыта HEAD: смены и расходы на объект больше не вносятся (и задним числом), чтобы цифры паспорта не поплыли.
ALTER TABLE objects ADD COLUMN IF NOT EXISTS closed_at timestamptz;
-- «Работы сданы» — день окончания работ (факт), его отмечает ГИП (или МОП, HEAD) в карточке проекта. В Битрикс
-- («Окончание факт») приложение пишет его при закрытии сделки HEAD — по нему выручка месяца.
ALTER TABLE objects ADD COLUMN IF NOT EXISTS done_on date,
                    ADD COLUMN IF NOT EXISTS done_by bigint REFERENCES people(id);

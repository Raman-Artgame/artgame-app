-- Отчёт таргетолога (HEAD 26.11 «да доработаем»): агентство загружает свой отчёт (Excel, PDF, скрин) — файл ложится на Диск
-- в «06 МАРКЕТИНГ / 04 ОТЧЁТЫ / Таргет / ГГГГ-ММ», рядом приложение ставит цифры Meta и Битрикса за тот же период,
-- HEAD — «Принято» или «Вернуть с вопросом». Ничего не удаляем.
CREATE TABLE IF NOT EXISTS mkt_ad_reports (
    id           bigserial PRIMARY KEY,
    period_from  date NOT NULL,
    period_to    date NOT NULL CHECK (period_to >= period_from),
    campaigns    text,                                   -- какие кампании, словами агентства
    note         text,                                   -- вывод агентства
    file_ids     bigint[] NOT NULL DEFAULT '{}',         -- файлы отчёта (files.kind='doc', object_id=0)
    rep_spend    numeric(14,2),                          -- «потрачено» из отчёта — для сверки с Meta
    rep_chats    integer,                                -- «переписки» из отчёта
    status       text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'returned')),
    author_id    bigint NOT NULL REFERENCES people(id),
    reviewed_by  bigint REFERENCES people(id),
    reviewed_at  timestamptz,
    review_note  text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mkt_ad_reports_status ON mkt_ad_reports (status, created_at DESC);

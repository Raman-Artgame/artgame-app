-- «Отложено» с датой возврата и уведомления бота (HEAD 05.11.2026). Битрикс — источник правды: в сделке остаётся
-- комментарий и задача с дедлайном; здесь — только когда и кому напомнить, и что уже отправлено.
CREATE TABLE bx_reminders (
    id         bigserial PRIMARY KEY,
    person_id  bigint NOT NULL REFERENCES people(id),
    deal_id    bigint NOT NULL,
    due        date NOT NULL,
    note       text,
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at    timestamptz
);
CREATE INDEX bx_reminders_due ON bx_reminders (due) WHERE sent_at IS NULL;

CREATE TABLE notices (
    person_id bigint NOT NULL REFERENCES people(id),
    key       text NOT NULL,
    sent_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (person_id, key)
);

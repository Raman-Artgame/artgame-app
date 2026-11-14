-- «Написать обращение» (HEAD 08.11): баги, доработки, вопросы от всех ролей → HEAD в «Пульте», ответ — в «Кабинете» и в Telegram.
CREATE TABLE IF NOT EXISTS feedback (
    id          bigserial PRIMARY KEY,
    person_id   bigint NOT NULL REFERENCES people(id),
    role_code   text,
    kind        text NOT NULL CHECK (kind IN ('bug', 'idea', 'question', 'other')),
    text        text NOT NULL,
    place       text,                       -- где в приложении (вкладка), если человек указал
    status      text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'work', 'done')),
    answer      text,
    answered_by bigint REFERENCES people(id),
    answered_at timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS feedback_status ON feedback (status, created_at DESC);
CREATE INDEX IF NOT EXISTS feedback_person ON feedback (person_id, created_at DESC);

-- HEAD 28.11: учебник и тесты в «Учёбе». Каждый ответ на вопрос теста и отметка «глава прочитана» — по человеку,
-- чтобы видеть, кто что освоил (и чтобы потом игра могла взять очки). Вопросы и ответы — в places/_study/*.enc.
CREATE TABLE IF NOT EXISTS study_answers (
  id        bigserial PRIMARY KEY,
  person_id bigint NOT NULL REFERENCES people(id),
  book      text NOT NULL,
  qid       text NOT NULL,
  ch        text NOT NULL,
  lvl       smallint NOT NULL,
  ok        boolean NOT NULL,
  at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS study_answers_person ON study_answers (person_id, book, qid, at DESC);

CREATE TABLE IF NOT EXISTS study_read (
  person_id bigint NOT NULL REFERENCES people(id),
  book      text NOT NULL,
  ch        text NOT NULL,
  at        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (person_id, book, ch)
);

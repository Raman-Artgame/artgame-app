-- Второй куратор ГИП на объекте (HEAD 28.11): права те же, что у первого.
ALTER TABLE objects ADD COLUMN IF NOT EXISTS gip2_person_id bigint REFERENCES people(id);

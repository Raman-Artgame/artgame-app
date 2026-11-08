-- Две роли у одного человека (HEAD 08.11, «Оба способа»): основная people.role_code + дополнительные.
-- Человек переключает «Я сейчас: …» (заголовок X-Act-Role), смена запоминает роль — ФОТ считает каждую смену по ставке её роли.
ALTER TABLE people ADD COLUMN IF NOT EXISTS extra_roles text[] NOT NULL DEFAULT '{}';
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS role_code text REFERENCES roles(code);

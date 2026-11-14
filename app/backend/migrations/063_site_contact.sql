-- Карточка проекта (HEAD 14.11): кто встречает на объекте. Имя видят все на проекте, телефон — ГИП, МОП и HEAD.
ALTER TABLE objects ADD COLUMN IF NOT EXISTS site_contact text;
ALTER TABLE objects ADD COLUMN IF NOT EXISTS site_phone text;

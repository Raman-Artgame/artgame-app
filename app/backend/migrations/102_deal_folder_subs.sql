-- HEAD 28.11 (вопрос Малики: «папка есть, а внутри нет папки Дизайн — создавать вручную?»): сторож папок проверяет и подпапки.
-- subs_at — когда у папки сделки проверены/досозданы подпапки (ДИЗАЙН, МЕДИА, ДОКУМЕНТЫ, РАСХОДЫ ЧЕКИ, ПРИХОДЫ ЧЕКИ).
ALTER TABLE deal_folders ADD COLUMN IF NOT EXISTS subs_at timestamptz;
ALTER TABLE deal_folders ADD COLUMN IF NOT EXISTS subs_error text;                 -- подпапки создать не вышло: видит HEAD на Пульте

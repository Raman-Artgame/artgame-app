-- Утверждение вместо WhatsApp (HEAD 14.11): готовый рилс / сторис грузят прямо в публикацию.
-- Вид файла «pub» — готовая публикация: лежит в «06 МАРКЕТИНГ / 04 Готовые публикации», в «Продакшн» и медиа объектов не попадает.
ALTER TABLE files DROP CONSTRAINT IF EXISTS files_kind_check;
ALTER TABLE files ADD CONSTRAINT files_kind_check CHECK (kind IN ('photo', 'design', 'receipt', 'doc', 'media', 'pub'));

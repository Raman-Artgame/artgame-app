-- Карточка проекта, строка маркетинга (HEAD 14.11): разрешил ли клиент публиковать объект. NULL — не спросили.
ALTER TABLE objects ADD COLUMN IF NOT EXISTS publish_ok boolean;

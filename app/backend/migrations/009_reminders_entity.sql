-- Напоминания и для лидов (05.11.2026): «перезвонить» из итога звонка.
ALTER TABLE bx_reminders ADD COLUMN IF NOT EXISTS entity text NOT NULL DEFAULT 'deal';

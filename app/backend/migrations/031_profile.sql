-- Анкета «Мои данные» (HEAD 09.11): имя в приложении — из анкеты, а не из Telegram. Заполняет сам человек.
ALTER TABLE people ADD COLUMN IF NOT EXISTS last_name text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS first_name text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS middle_name text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS birth_date date;
ALTER TABLE people ADD COLUMN IF NOT EXISTS emergency_name text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS emergency_phone text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS clothes_size text;
ALTER TABLE people ADD COLUMN IF NOT EXISTS profile_at timestamptz;

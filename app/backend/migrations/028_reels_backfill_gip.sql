-- HEAD 09.11: «Оплачиваемые рилс» любому человеку (Глеб); смены и расходы задним числом с 1.11 (до срока HEAD); ГИП на проект.
ALTER TABLE people ADD COLUMN IF NOT EXISTS reels boolean NOT NULL DEFAULT false;
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS backfill boolean NOT NULL DEFAULT false;
ALTER TABLE expenses ADD COLUMN IF NOT EXISTS backfill boolean NOT NULL DEFAULT false;

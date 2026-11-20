-- HEAD 11.11: «Как мне его посмотреть? Что я утверждаю?» — сколько работ в каталоге пишет дизайнер.
ALTER TABLE design_catalogs ADD COLUMN IF NOT EXISTS works int;

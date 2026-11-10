-- Смена по роли (очередь 1, шаг 1). Печать: принтер, бонус сверх плана. Роспись: условия, норма, КПД.
-- Норму и бонус считает сервер из «Значений» в момент отправки и хранит в смене (цифры на тот день).
ALTER TABLE shifts
    ADD COLUMN printer      text,
    ADD COLUMN at_height    boolean NOT NULL DEFAULT false,
    ADD COLUMN outdoor      boolean NOT NULL DEFAULT false,
    ADD COLUMN hard_surface boolean NOT NULL DEFAULT false,
    ADD COLUMN plan_m2      numeric(10,2),   -- норма (роспись) или план (печать) на эту смену
    ADD COLUMN kpd          numeric(6,3),    -- сделано / норма
    ADD COLUMN bonus        numeric(12,2);   -- печать: бонус сверх плана (видят сам человек и HEAD)

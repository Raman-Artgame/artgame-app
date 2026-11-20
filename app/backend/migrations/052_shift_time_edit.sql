-- Время в текущей смене (HEAD 11.11, «с пометкой»): «Начал раньше?» / «Закончил раньше?» — сотрудник ставит своё время.
-- Сдвиг больше 30 мин от нажатия — пометка, её видят куратор и HEAD. Нажатие — время телефона (офлайн-очередь шлёт позже).
ALTER TABLE shifts ADD COLUMN IF NOT EXISTS time_edited boolean NOT NULL DEFAULT false,
                   ADD COLUMN IF NOT EXISTS time_note   text;

-- HEAD 13.11: «Арслан сдал экзамен — принтерные работы с ноября по 15 000, саппортом — 10 000».
-- День, с которого оператор печати получает ставку после экзамена (pay.print.operator_exam). Пусто — экзамен не сдан.
ALTER TABLE people ADD COLUMN IF NOT EXISTS print_exam_on date;

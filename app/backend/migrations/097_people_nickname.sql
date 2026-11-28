-- HEAD 27.11: имена сотрудников — «Имя Фамилия» и никнейм. Никнейм — отдельное поле (творческое имя, как человека зовут в команде).
ALTER TABLE people ADD COLUMN IF NOT EXISTS nickname text;

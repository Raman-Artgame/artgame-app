-- «Исполняет обязанности» (HEAD 09.11): художник уже работает Главным, ставка пока прежняя — повышение в назначенный день.
-- Права, меню и «Правила игры» — по acting_role; ставки и ФОТ — по role_code. Повышение HEAD делает сам: меняет роль в «Команде».
ALTER TABLE people
  ADD COLUMN IF NOT EXISTS acting_role  text REFERENCES roles(code),
  ADD COLUMN IF NOT EXISTS acting_since date,
  ADD COLUMN IF NOT EXISTS acting_promo date,
  ADD COLUMN IF NOT EXISTS acting_note  text;

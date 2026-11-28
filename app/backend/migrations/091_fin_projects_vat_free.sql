-- HEAD 26.11: НДС есть только у сделок через ИП Яковлев. Сделки через ИП Артамонов и «Без документов» — вся сумма без вычета.
-- Признак ставит синхронизация сданных сделок из Битрикса (fin_bx.import_projects) по полю «Реквизиты моей компании».
ALTER TABLE fin_projects ADD COLUMN IF NOT EXISTS vat_free boolean NOT NULL DEFAULT false;

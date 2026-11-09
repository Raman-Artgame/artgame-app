-- HEAD 09.11: «Тест · Саппорт / Художник…» — убрать отовсюду, прямо удалить. Тестовые сотрудники режима «Пройти как сотрудник»
-- (tg_id < 0, имя «Тест · …») и всё, что они сделали: смены, фото, расходы, начисления, записи журнала, просмотры test:.
-- Функцию же вызывает кнопка «Стереть тестовые данные» в «Смотреть как» (viewas.purge). Файлы на Google Диске не трогаются.
CREATE OR REPLACE FUNCTION purge_test_people() RETURNS integer LANGUAGE plpgsql AS $$
DECLARE
  tp bigint[]; ts bigint[]; te bigint[]; tf bigint[]; n integer; r record;
BEGIN
  SELECT coalesce(array_agg(id), '{}') INTO tp FROM people WHERE tg_id < 0 AND full_name LIKE 'Тест · %';
  IF cardinality(tp) = 0 THEN
    DELETE FROM audit_log WHERE action IN ('view_as_start', 'view_as_stop') AND data->>'target' LIKE 'test:%';
    RETURN 0;
  END IF;
  SELECT coalesce(array_agg(id), '{}') INTO ts FROM shifts WHERE person_id = ANY(tp);
  SELECT coalesce(array_agg(id), '{}') INTO te FROM expenses WHERE person_id = ANY(tp);
  SELECT coalesce(array_agg(id), '{}') INTO tf FROM files WHERE uploaded_by = ANY(tp);
  -- журнал: их действия, решения по их сменам и расходам, входы HEAD в тест
  DELETE FROM audit_log WHERE person_id = ANY(tp)
     OR (entity = 'shifts' AND entity_id = ANY(SELECT x::text FROM unnest(ts) x))
     OR (entity IN ('expenses', 'expense') AND entity_id = ANY(SELECT x::text FROM unnest(te) x))
     OR (entity = 'files' AND entity_id = ANY(SELECT x::text FROM unnest(tf) x))
     OR (action IN ('view_as_start', 'view_as_stop') AND data->>'target' LIKE 'test:%');
  DELETE FROM shift_photos WHERE shift_id = ANY(ts) OR file_id = ANY(tf);
  UPDATE shifts SET photo_before = NULL WHERE photo_before = ANY(tf) AND NOT id = ANY(ts);
  UPDATE shifts SET photo_after = NULL WHERE photo_after = ANY(tf) AND NOT id = ANY(ts);
  DELETE FROM stock_lines WHERE expense_id = ANY(te);
  DELETE FROM fin_ledger WHERE expense_id = ANY(te) OR receipt_file_id = ANY(tf) OR created_by = ANY(tp);
  DELETE FROM expenses WHERE id = ANY(te);
  UPDATE expenses SET receipt_file_id = NULL WHERE receipt_file_id = ANY(tf);
  DELETE FROM shifts WHERE id = ANY(ts);
  DELETE FROM fin_accruals WHERE payee_id IN (SELECT id FROM fin_payees WHERE person_id = ANY(tp)) OR created_by = ANY(tp);
  DELETE FROM fin_payees WHERE person_id = ANY(tp);
  DELETE FROM files WHERE id = ANY(tf);
  -- прочие ссылки на тестовых: необязательные — обнулить, обязательные — удалить строку
  FOR r IN SELECT c.conrelid::regclass AS t, a.attname AS col, a.attnotnull AS nn FROM pg_constraint c
           JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
           WHERE c.contype = 'f' AND c.confrelid = 'people'::regclass LOOP
    IF r.nn THEN EXECUTE format('DELETE FROM %s WHERE %I = ANY($1)', r.t, r.col) USING tp;
    ELSE EXECUTE format('UPDATE %s SET %I = NULL WHERE %I = ANY($1)', r.t, r.col, r.col) USING tp; END IF;
  END LOOP;
  DELETE FROM people WHERE id = ANY(tp);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

SELECT purge_test_people();

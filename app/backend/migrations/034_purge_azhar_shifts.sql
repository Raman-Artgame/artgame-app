-- HEAD 09.11: «Ажар поставила дорогу 10 числа… Давай удалим все её записи и пусть заново сделает все по всем дням».
-- Удаляются все смены и дороги Ажар (с фото смен и записями журнала по ним). Расходы и анкета не трогаются,
-- файлы на Диске остаются. Сделано один раз: если Ажар не найдена или найдено больше одной — ничего не удаляется.
DO $$
DECLARE pid bigint; n int; ts bigint[];
BEGIN
  SELECT count(*), min(id) INTO n, pid FROM people
   WHERE (full_name ILIKE '%Ажар%' OR full_name ILIKE '%Azhar%') AND coalesce(tg_id, 0) > 0;
  IF n <> 1 THEN RAISE NOTICE 'Ажар найдено %, пропуск', n; RETURN; END IF;
  SELECT coalesce(array_agg(id), '{}') INTO ts FROM shifts WHERE person_id = pid;
  DELETE FROM shift_photos WHERE shift_id = ANY(ts);
  DELETE FROM audit_log WHERE entity = 'shifts' AND entity_id = ANY(SELECT x::text FROM unnest(ts) x);
  DELETE FROM shifts WHERE id = ANY(ts);
  INSERT INTO audit_log (person_id, action, entity, entity_id, data)
  VALUES (NULL, 'shifts_purge', 'people', pid::text, jsonb_build_object('shifts', cardinality(ts), 'by', 'HEAD 09.11: удалить все записи, внесёт заново'));
END $$;

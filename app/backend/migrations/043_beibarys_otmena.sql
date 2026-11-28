-- HEAD 11.11: «Отмени пока что все траты Бейбарыса вообще. Я ему скажу, чтобы он чётко прислал за ноябрь».
-- Все 11 трат внесены 11.11 ночью задним числом (01–08.11), одна из них — доставка от 8 октября (за октябрь уже платили).
-- Отменяем все его неотменённые и ещё не выплаченные траты: статус «отменено», из «К выплате» убираются.
-- Строки не удаляются. Ровно один человек «Бейбарыс», иначе ничего не меняется. Журнал: expense_fix.
DO $$
DECLARE pid bigint; n int; e record;
BEGIN
  SELECT count(*) INTO n FROM people WHERE full_name ILIKE '%Бейбарыс%';
  IF n <> 1 THEN RAISE NOTICE 'Бейбарыс: найдено людей %, пропуск', n; RETURN; END IF;
  SELECT id INTO pid FROM people WHERE full_name ILIKE '%Бейбарыс%';
  FOR e IN SELECT * FROM expenses WHERE person_id = pid AND status <> 'cancelled' AND payout_status <> 'paid' LOOP
    UPDATE expenses SET status = 'cancelled', payout_status = 'none',
           reason = 'HEAD 11.11: отменено целиком, внести заново только ноябрь с датами поездок'
     WHERE id = e.id;
    INSERT INTO audit_log (person_id, action, entity, entity_id, data)
    VALUES (NULL, 'expense_fix', 'expenses', e.id::text,
            jsonb_build_object('from', jsonb_build_array(e.status, e.payout_status, e.amount), 'to', 'cancelled',
                               'by', 'HEAD 11.11: все траты Бейбарыса отменить, пусть пришлёт только ноябрь'));
  END LOOP;
END $$;

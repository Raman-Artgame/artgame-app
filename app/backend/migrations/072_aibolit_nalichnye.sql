-- HEAD 16.11: «По айболиту нужно заменить оплату на наличные Анна неправильно написала». ТЦ АЙБОЛИТ — КАРАГАНДА (1347):
-- аванс 50% 800 000 от 09.11 Анна внесла на счёт «Переводы HEAD», а клиент платил наличными. Меняем только счёт этой одной
-- оплаты на «Наличные»: сумма, дата, чек и отметка HEAD остаются, «Поступило» и долг сделки те же (в Битрикс уходят только
-- итоги, счёт туда не пишется). Ровно одна такая строка, иначе ничего не меняется. Журнал: ledger_fix.
DO $$
DECLARE n int; r record;
BEGIN
  SELECT count(*) INTO n FROM fin_ledger
   WHERE deal_id = 1347 AND source = 'app' AND status = 'active' AND direction = 'in' AND transfer_id IS NULL
     AND amount = 800000 AND op_date = '2026-11-09' AND account_code = 'head';
  IF n <> 1 THEN RAISE NOTICE 'Айболит 1347, аванс 800 000 от 09.11 на «Переводы HEAD»: найдено строк %, пропуск', n; RETURN; END IF;
  SELECT * INTO r FROM fin_ledger
   WHERE deal_id = 1347 AND source = 'app' AND status = 'active' AND direction = 'in' AND transfer_id IS NULL
     AND amount = 800000 AND op_date = '2026-11-09' AND account_code = 'head';
  UPDATE fin_ledger SET account_code = 'cash' WHERE id = r.id;
  INSERT INTO audit_log (person_id, action, entity, entity_id, data)
  VALUES (NULL, 'ledger_fix', 'fin_ledger', r.id::text,
          jsonb_build_object('deal', 1347, 'amount', r.amount, 'from', 'head', 'to', 'cash',
                             'by', 'HEAD 16.11: аванс Айболита — наличные, Анна внесла как «Переводы HEAD»'));
END $$;

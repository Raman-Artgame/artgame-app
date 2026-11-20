-- HEAD 11.11 «да»: ФОК — АТЫРАУ (943), аванс 1 276 000 Анна внесла датой 11.11 на «Kaspi ИП Яковлев», а по сделке он пришёл
-- 21.10 («Поступление 1»). Переносим эту одну оплату на 21.10 в счёт «История (до ноября)», как вносится оплата до ноября:
-- «Поступило» и долг сделки не меняются, из денег ноября и остатка Kaspi уходит 1 276 000. Чек и отметка HEAD остаются.
-- Ровно одна такая строка, иначе ничего не меняется. Журнал: ledger_fix.
DO $$
DECLARE n int; r record;
BEGIN
  SELECT count(*) INTO n FROM fin_ledger
   WHERE deal_id = 943 AND source = 'app' AND status = 'active' AND direction = 'in'
     AND amount = 1276000 AND op_date = '2026-11-11' AND account_code = 'kaspi';
  IF n <> 1 THEN RAISE NOTICE 'ФОК 943, аванс 1 276 000 от 11.11: найдено строк %, пропуск', n; RETURN; END IF;
  SELECT * INTO r FROM fin_ledger
   WHERE deal_id = 943 AND source = 'app' AND status = 'active' AND direction = 'in'
     AND amount = 1276000 AND op_date = '2026-11-11' AND account_code = 'kaspi';
  UPDATE fin_ledger
     SET op_date = '2026-10-21', account_code = 'hist', period = '2026-10',
         note = CASE WHEN note LIKE '%до ноября%' THEN note ELSE replace(note, ' · Аванс', ' · до ноября · Аванс') END
   WHERE id = r.id;
  INSERT INTO audit_log (person_id, action, entity, entity_id, data)
  VALUES (NULL, 'ledger_fix', 'fin_ledger', r.id::text,
          jsonb_build_object('deal', 943, 'amount', r.amount,
                             'from', jsonb_build_array(r.op_date, r.account_code, r.period),
                             'to', jsonb_build_array('2026-10-21', 'hist', '2026-10'),
                             'by', 'HEAD 11.11 «да»: аванс ФОК пришёл 21.10, а не 11.11 — в «Историю»'));
END $$;

-- HEAD 10.11: «Расходы Елизаветы Звягиной на Айболит нужно отменить 35000, так как мы оплачивали».
-- Её чек «свои деньги» 35 000 по Айболиту не возмещаем. Если та же трата уже записана как расход компании в журнале денег
-- по этой сделке — чек отменяется (иначе задвоится). Если нет — остаётся расходом проекта как «деньги компании».
-- Строго одна подходящая запись, иначе ничего не меняется. Журнал: expense_fix.
DO $$
DECLARE e record; n int; dup boolean;
BEGIN
  SELECT count(*) INTO n FROM expenses x JOIN people pe ON pe.id = x.person_id JOIN objects o ON o.id = x.object_id
   WHERE pe.full_name ILIKE '%Звягин%' AND o.title ILIKE '%АЙБОЛИТ%' AND x.amount = 35000 AND x.status <> 'cancelled';
  IF n <> 1 THEN RAISE NOTICE 'Звягина / Айболит 35000: найдено %, пропуск', n; RETURN; END IF;
  SELECT x.* INTO e FROM expenses x JOIN people pe ON pe.id = x.person_id JOIN objects o ON o.id = x.object_id
   WHERE pe.full_name ILIKE '%Звягин%' AND o.title ILIKE '%АЙБОЛИТ%' AND x.amount = 35000 AND x.status <> 'cancelled';
  dup := EXISTS (SELECT 1 FROM fin_ledger WHERE status = 'active' AND direction = 'out' AND amount = 35000
                  AND deal_id = e.object_id AND expense_id IS DISTINCT FROM e.id);
  IF dup THEN
    UPDATE expenses SET status = 'cancelled', payout_status = 'none', reason = 'HEAD 10.11: оплачено компанией, уже в журнале денег' WHERE id = e.id;
  ELSE
    UPDATE expenses SET paid_by = 'company', payout_status = 'none' WHERE id = e.id;
  END IF;
  INSERT INTO audit_log (person_id, action, entity, entity_id, data)
  VALUES (NULL, 'expense_fix', 'expenses', e.id::text, jsonb_build_object('from', jsonb_build_array(e.paid_by, e.status, e.payout_status),
          'to', CASE WHEN dup THEN 'cancelled' ELSE 'company' END, 'by', 'HEAD 10.11: Айболит 35000 оплачивали мы'));
END $$;

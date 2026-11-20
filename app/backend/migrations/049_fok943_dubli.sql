-- HEAD 11.11: «эти нужно удалить, мы заново нормально все внесли с чеками». ФОК — АТЫРАУ (943): оплаты 21.10 (1 276 000)
-- и 28.10 (1 914 000) из полей «Поступление 1–2» Анна внесла заново в приложении с чеками; строки из полей задваивали
-- «Поступило» (10 380 000 вместо 7 190 000, «переплата» 592 500). Отменяем ровно эти две строки: не удаляем, статус «отменено»;
-- импорт из полей отменённую строку обратно не возвращает. Журнал: ledger_fix.
DO $$
DECLARE r record;
BEGIN
  FOR r IN SELECT * FROM fin_ledger
            WHERE deal_id = 943 AND source = 'bitrix' AND status = 'active'
              AND ((source_ref = 'deal:943:pay1' AND amount = 1276000 AND op_date = '2026-10-21')
                OR (source_ref = 'deal:943:pay2' AND amount = 1914000 AND op_date = '2026-10-28')) LOOP
    UPDATE fin_ledger SET status = 'cancelled' WHERE id = r.id;
    INSERT INTO audit_log (person_id, action, entity, entity_id, data)
    VALUES (NULL, 'ledger_fix', 'fin_ledger', r.id::text,
            jsonb_build_object('deal', 943, 'ref', r.source_ref, 'amount', r.amount, 'op_date', r.op_date, 'to', 'cancelled',
                               'by', 'HEAD 11.11: оплаты ФОК внесены заново с чеками, строки из полей «Поступление» убрать'));
  END LOOP;
END $$;

-- HEAD 11.11 «1409 нужно удалить это же тест?»: 1409 «ТЕСТ ARTGAME — ДОКУМЕНТЫ — НЕ КЛИЕНТ — АЛМАТЫ» — тестовая сделка,
-- закрыта проигранной 08.11 (стадия «Другое»). Её «Поступление 2» без даты импорт 10.11 записал приходом ноября
-- (50 000, Kaspi ИП Яковлев) — оно попало в «Пришло» Пульта и в остаток Kaspi. Отменяем все живые строки журнала по этой
-- сделке (статус «отменено», ничего не удаляем). Импорт отменённую строку не возвращает, тестовые сделки больше не читает.
-- Журнал: ledger_fix.
DO $$
DECLARE n int := 0; r record;
BEGIN
  FOR r IN SELECT * FROM fin_ledger
            WHERE deal_id = 1409 AND status = 'active' AND note LIKE '%ТЕСТ ARTGAME%' ORDER BY id LOOP
    UPDATE fin_ledger SET status = 'cancelled' WHERE id = r.id;
    INSERT INTO audit_log (person_id, action, entity, entity_id, data)
    VALUES (NULL, 'ledger_fix', 'fin_ledger', r.id::text,
            jsonb_build_object('deal', 1409, 'amount', r.amount, 'op_date', r.op_date, 'account', r.account_code,
                               'source', r.source, 'source_ref', r.source_ref, 'to', 'cancelled',
                               'by', 'HEAD 11.11: 1409 — тестовая сделка, её оплата не деньги'));
    n := n + 1;
  END LOOP;
  RAISE NOTICE 'Тест 1409: отменено строк журнала %', n;
END $$;

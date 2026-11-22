-- HEAD 22.11 08:57 UTC (тред «Упростить Битрикс и перенести оплаты в приложение»): «ну так сделай то что нужно я подтверждаю» —
-- ответ на «9 ноябрьских оплат из таблицы стоят «на сверке», их нужно отметить ✓». Это оплаты, которые миграция 074 внесла
-- по таблице Алины без чека: 833, 1273 — Kaspi ИП Яковлев; 981 (пять), 1091, 1693 — ИП Артамонов. Отмечаем их сверенными,
-- как ✓ HEAD в «Проверке»: checked_at = now(). Сумма, дата, счёт и «Поступило»/«Долг» сделки не меняются — оплата на сверке
-- уже считается (deal_money.COUNT_UNCHECKED). Только строки 074 (source 'app', «по таблице Алины», активные, ещё не сверенные);
-- каждая — ровно одна, иначе пропуск (NOTICE): уже сверенную или отменённую (✕) HEAD не трогаем. В базе без этих строк
-- (тесты, новая среда) — ничего. Журнал: audit_log client_payment_check.
DO $$
DECLARE
  plan jsonb := '[
    [833, "2026-11-11", 2000000, "kaspi"],
    [1273, "2026-11-10", 3750000, "kaspi"],
    [981, "2026-11-03", 100000, "artamonov"],
    [981, "2026-11-05", 100000, "artamonov"],
    [981, "2026-11-09", 100000, "artamonov"],
    [981, "2026-11-10", 100000, "artamonov"],
    [981, "2026-11-12", 50000, "artamonov"],
    [1091, "2026-11-16", 5260000, "artamonov"],
    [1693, "2026-11-12", 150000, "artamonov"]
  ]';
  x jsonb; n int; rid bigint; done int := 0;
BEGIN
  FOR x IN SELECT * FROM jsonb_array_elements(plan) LOOP
    SELECT count(*) INTO n FROM fin_ledger
     WHERE deal_id = (x->>0)::bigint AND op_date = (x->>1)::date AND amount = (x->>2)::numeric AND account_code = x->>3
       AND source = 'app' AND status = 'active' AND direction = 'in' AND article_code = 'client_payment'
       AND checked_at IS NULL AND note LIKE '%по таблице Алины%';
    IF n <> 1 THEN
      IF n > 1 OR EXISTS (SELECT 1 FROM fin_ledger WHERE deal_id = (x->>0)::bigint AND op_date = (x->>1)::date
                           AND amount = (x->>2)::numeric AND source = 'app' AND note LIKE '%по таблице Алины%') THEN
        RAISE NOTICE 'Ноябрьские оплаты Алины, сделка % от % на %: на сверке строк %, пропуск', x->>0, x->>1, x->>2, n;
      END IF;
      CONTINUE;
    END IF;
    UPDATE fin_ledger SET checked_at = now()
     WHERE deal_id = (x->>0)::bigint AND op_date = (x->>1)::date AND amount = (x->>2)::numeric AND account_code = x->>3
       AND source = 'app' AND status = 'active' AND direction = 'in' AND article_code = 'client_payment'
       AND checked_at IS NULL AND note LIKE '%по таблице Алины%'
    RETURNING id INTO rid;
    INSERT INTO audit_log (person_id, action, entity, entity_id, data)
    VALUES (NULL, 'client_payment_check', 'fin_ledger', rid::text,
            jsonb_build_object('deal', (x->>0)::bigint, 'amount', (x->>2)::numeric, 'op_date', x->>1, 'account', x->>3,
                               'by', 'HEAD 22.11 08:57 UTC «я подтверждаю»: ноябрьские оплаты по таблице Алины'));
    done := done + 1;
  END LOOP;
  IF done > 0 THEN
    RAISE NOTICE 'Ноябрьские оплаты Алины: отмечено сверенными % из 9', done;
  END IF;
END $$;

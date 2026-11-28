-- HEAD 17.11 01:41 UTC «да» по сверке с таблицей Алины («Учет финансов Алина!!!», HEAD 16.11: «информация актуальная, нужно её закинуть
-- по сделкам и фин таблице»; ответы Алины 17.11). Оплаты 32 сделок — как у Алины: строки из полей «Поступление 1–4»,
-- которые она не подтверждает, отменяем (не удаляем, статус «отменено»), её оплаты вносим с её датами. До ноября — счёт
-- «История (до ноября)», сразу сверены; ноябрьские (833, 1273 — Kaspi ИП Яковлев; 981, 1091, 1693 — ИП Артамонов) без чека, их сверяет HEAD.
-- Новая оплата занимает своё «Поступление N» (как «Дата и чек»): поле сделки больше не читается, двойного счёта нет;
-- оплаты сверх четырёх полей — без «Поступления N», как внесённые в приложении.
-- По каждой сделке — всё или ничего: «поступило» по журналу должно быть ровно как при сверке 16.11, каждая отменяемая
-- строка — ровно одна, иначе сделка пропускается (NOTICE); в базе без этой истории ничего не меняется. Суммы, стадии
-- и компанию в Битриксе меняет задача на сервере с кнопкой HEAD; «Поступило» и «Долг» приложение запишет в сделку само.
-- Копии старых данных — в Архиве 2026 на Диске. Журнал: ledger_fix.
DO $$
DECLARE
  plan jsonb := '[
    {"deal":677,"title":"677 · СТАДИОН — АСТАНА","was":8370000,"cancel":[[1,8370000,"2026-03-14"]],"add":[[1,"2026-04-28",1800000,"hist",""],[2,"2026-07-09",2000000,"hist",""]]},
    {"deal":833,"title":"833 · ЛАГЕРЬ — КЫЗЫЛОРДА","was":20549192,"cancel":[[1,20549192,"2026-04-17"]],"add":[[1,"2026-04-16",3000000,"hist",""],[2,"2026-06-12",2917000,"hist",""],[3,"2026-08-21",9000000,"hist",""],[4,"2026-11-11",2000000,"kaspi",""]]},
    {"deal":869,"title":"869 · ОРАНЖЕРЕЯ — КЫЗЫЛОРДА","was":5236240,"cancel":[[1,5236240,"2026-06-01"]],"add":[[1,"2026-07-30",5079152,"hist",""]]},
    {"deal":1281,"title":"1281 · ЖК ТАМГА, 20 КАРТИН — АЛМАТЫ","was":1470000,"cancel":[[1,1267000,"2026-09-01"],[2,203000,"2026-08-13"]],"add":[[1,"2026-08-06",735000,"hist",""]]},
    {"deal":1109,"title":"1109 · ТРЦ N-CITY — АСТАНА","was":1500000,"cancel":[[1,1500000,"2026-09-28"]],"add":[[1,"2026-09-25",870000,"hist",""]]},
    {"deal":1113,"title":"1113 · БОЛЬНИЦА №2 BI — АСТАНА","was":5040000,"cancel":[[1,5040000,"2026-09-01"]],"add":[]},
    {"deal":1145,"title":"1145 · ПАРКИНГ ЖК ИЗБАСАР — АСТАНА","was":696000,"cancel":[[1,696000,"2026-08-15"]],"add":[[1,"2026-10-19",661200,"hist",""]]},
    {"deal":1275,"title":"1275 · ПАРКИНГ ГРАНД ПАРК ВИТА — ШЫМКЕНТ","was":900000,"cancel":[[1,900000,"2026-09-01"]],"add":[]},
    {"deal":1571,"title":"1571 · ЖК 4YOU ПАРКИНГ — ШЫМКЕНТ","was":2961480,"cancel":[[1,2961480,"2026-08-22"]],"add":[]},
    {"deal":931,"title":"931 · ТРАНСФОРМАТОРНЫЕ БУДКИ BI JOY — ШЫМКЕНТ","was":1045000,"cancel":[[1,1045000,"2026-08-04"]],"add":[]},
    {"deal":1445,"title":"1445 · ПАРКИНГ АУЛЕТ — ШЫМКЕНТ","was":0,"cancel":[],"add":[[1,"2026-10-19",600300,"hist",""]]},
    {"deal":981,"title":"981 · КИТАЙСКАЯ ШКОЛА — АСТАНА","was":5645000,"cancel":[[1,5645000,"2026-08-01"]],"add":[[1,"2026-07-27",1320000,"hist",""],[2,"2026-08-18",955000,"hist","из 1 320 000, 365 000 — овал One Hub"],[3,"2026-08-25",1200000,"hist",""],[4,"2026-09-21",730000,"hist",""],[null,"2026-10-07",300000,"hist",""],[null,"2026-10-14",70000,"hist","из 200 000, 130 000 — оранжевая стена 1575"],[null,"2026-10-28",100000,"hist",""],[null,"2026-11-03",100000,"artamonov",""],[null,"2026-11-05",100000,"artamonov",""],[null,"2026-11-09",100000,"artamonov",""],[null,"2026-11-10",100000,"artamonov",""],[null,"2026-11-12",50000,"artamonov",""]]},
    {"deal":1283,"title":"1283 · КАРТИНЫ 60 ШТ ЭЛЬМОНТЕ БИАЙ — АЛМАТЫ","was":3620000,"cancel":[[1,3620000,"2026-09-01"]],"add":[[1,"2026-07-31",2100000,"hist",""]]},
    {"deal":1091,"title":"1091 · ШКОЛА — АСТАНА","was":10500000,"cancel":[[1,10000000,"2026-08-09"],[2,500000,"2026-08-31"]],"add":[[1,"2026-08-16",2500000,"hist","переводы 15–16.08 на номер Raman K."],[2,"2026-08-22",1400000,"hist","наличными Алине"],[3,"2026-08-28",2000000,"hist","наличными, принёс Владимир"],[4,"2026-10-02",4000000,"hist",""],[null,"2026-10-14",4000000,"hist",""],[null,"2026-10-29",3000000,"hist","наличными Раману"],[null,"2026-11-16",5260000,"artamonov",""]]},
    {"deal":1693,"title":"1693 · АКАДЕМИЯ БОЛАШАК — КАРАГАНДА","was":0,"cancel":[],"add":[[1,"2026-11-12",150000,"artamonov",""]]},
    {"deal":489,"title":"489 · СТЕНА ПОД КАМЕНЬ — ШЫМКЕНТ","was":250000,"cancel":[[2,25000,"2026-02-11"]],"add":[]},
    {"deal":545,"title":"545 · ЛАУНЖ-БАР — АСТАНА","was":2000000,"cancel":[[1,2000000,"2026-03-01"]],"add":[[1,"2026-03-01",1700000,"hist",""]]},
    {"deal":1565,"title":"1565 · ЖАНЫМ СОЛ ЦЕПИ — АСТАНА","was":615000,"cancel":[[1,615000,"2026-03-22"]],"add":[[1,"2026-03-22",418000,"hist",""]]},
    {"deal":777,"title":"777 · ДЕТСКИЙ МЕДИЦИНСКИЙ ЦЕНТР ФИДЕС — АСТАНА","was":1675000,"cancel":[[1,1675000,"2026-04-02"]],"add":[[1,"2026-04-02",1764000,"hist",""]]},
    {"deal":873,"title":"873 · ЖК ДЕНДРОПАРК — ШЫМКЕНТ","was":725000,"cancel":[[1,725000,"2026-06-01"]],"add":[[1,"2026-08-13",841000,"hist",""]]},
    {"deal":1263,"title":"1263 · КАБИНЕТ ИНФОРМАТИКИ — АСТАНА","was":420000,"cancel":[[1,420000,"2026-10-15"]],"add":[[1,"2026-10-15",487200,"hist",""]]},
    {"deal":1273,"title":"1273 · ПОДЪЕЗДЫ GALAMAT — АСТАНА","was":3400000,"cancel":[[1,3400000,"2026-09-01"]],"add":[[1,"2026-11-10",3750000,"kaspi",""]]},
    {"deal":967,"title":"967 · ШКОЛА — ШАХТИНСК","was":715000,"cancel":[[1,715000,"2026-10-07"]],"add":[[1,"2026-09-23",829400,"hist",""]]},
    {"deal":577,"title":"577 · РЕНТГЕН-КАБИНЕТ СТОМАТОЛОГИИ — АСТАНА","was":330000,"cancel":[[2,200000,"2026-08-14"]],"add":[]},
    {"deal":831,"title":"831 · ТЦ ЖИБЕК ЖОЛЫ — АСТАНА","was":14981000,"cancel":[[1,14981000,"2026-04-01"]],"add":[[1,"2026-04-01",14981600,"hist",""]]},
    {"deal":835,"title":"835 · МУЗЫКАЛЬНАЯ ШКОЛА — АСТАНА","was":506000,"cancel":[[1,506000,"2026-05-04"]],"add":[[1,"2026-05-04",506800,"hist",""]]},
    {"deal":875,"title":"875 · ШКОЛА №75 — АСТАНА","was":661000,"cancel":[[1,661000,"2026-06-03"]],"add":[[1,"2026-06-11",331600,"hist",""],[2,"2026-07-09",330000,"hist",""]]},
    {"deal":1007,"title":"1007 · ПОЖАРНАЯ ЧАСТЬ — АСТАНА","was":1149000,"cancel":[[1,1149000,"2026-07-29"]],"add":[[1,"2026-07-29",1149119,"hist",""]]},
    {"deal":1187,"title":"1187 · МАГАЗИН БЕЛЫЙ ВЕТЕР — КАРАГАНДА","was":175000,"cancel":[[2,175000,"2026-09-06"]],"add":[[2,"2026-09-06",174000,"hist",""]]},
    {"deal":1575,"title":"1575 · БЦ ONE HUB ОРАНЖ СТЕНА — АСТАНА","was":100000,"cancel":[[1,100000,"2026-10-10"]],"add":[[1,"2026-10-14",130000,"hist","со счёта школы QCS, из 200 000"]]},
    {"deal":871,"title":"871 · ДЕТСКАЯ КОМНАТА URBAN HILLS — ШЫМКЕНТ","was":488000,"cancel":[[1,488000,"2026-06-05"]],"add":[[1,"2026-06-04",244000,"hist",""],[2,"2026-07-09",310000,"hist",""]]},
    {"deal":1479,"title":"1479 · ПАРКИНГ ГОРОД — ШЫМКЕНТ","was":376000,"cancel":[[1,188000,"2026-01-01"],[2,188000,"2026-03-07"]],"add":[[1,"2026-02-07",188000,"hist",""]]}
  ]';
  p jsonb; c jsonb; a jsonb; did bigint; n int; tot numeric; why text; rid bigint; ref text; day date; hist boolean;
  known int := 0;
BEGIN
  -- база без истории оплат 2026 (новая среда, тесты): ни одна сделка не сходится со сверкой — ничего не делаем,
  -- иначе сделки, где при сверке оплат не было (1445, 1693), получили бы оплаты в чужой базе
  FOR p IN SELECT * FROM jsonb_array_elements(plan) WHERE (value->>'was')::numeric > 0 LOOP
    SELECT coalesce(sum(CASE WHEN direction = 'in' THEN amount ELSE -amount END), 0) INTO tot FROM fin_ledger
     WHERE deal_id = (p->>'deal')::bigint AND status = 'active' AND article_code IN ('client_payment', 'design_prepay', 'refund');
    IF tot = (p->>'was')::numeric THEN known := known + 1; END IF;
  END LOOP;
  IF known = 0 THEN
    RAISE NOTICE 'Сверка Алины: в журнале нет оплат, как при сверке 16.11, — пропуск';
    RETURN;
  END IF;
  FOR p IN SELECT * FROM jsonb_array_elements(plan) LOOP
    did := (p->>'deal')::bigint; why := NULL;
    SELECT coalesce(sum(CASE WHEN direction = 'in' THEN amount ELSE -amount END), 0) INTO tot FROM fin_ledger
     WHERE deal_id = did AND status = 'active' AND article_code IN ('client_payment', 'design_prepay', 'refund');
    IF tot <> (p->>'was')::numeric THEN
      why := format('поступило по журналу %s, при сверке было %s', tot, p->>'was');
    END IF;
    IF why IS NULL THEN
      FOR c IN SELECT * FROM jsonb_array_elements(p->'cancel') LOOP
        SELECT count(*) INTO n FROM fin_ledger
         WHERE deal_id = did AND source = 'bitrix' AND status = 'active' AND direction = 'in'
           AND source_ref = format('deal:%s:pay%s', did, c->>0) AND amount = (c->>1)::numeric AND op_date = (c->>2)::date;
        IF n <> 1 THEN why := format('«Поступление %s» %s от %s: строк %s', c->>0, c->>1, c->>2, n); EXIT; END IF;
      END LOOP;
    END IF;
    IF why IS NULL THEN
      FOR a IN SELECT * FROM jsonb_array_elements(p->'add') LOOP
        IF a->>0 IS NOT NULL AND EXISTS (SELECT 1 FROM fin_ledger WHERE source = 'app' AND source_ref = format('deal:%s:pay%s', did, a->>0)) THEN
          why := format('«Поступление %s» уже заменено оплатой из приложения', a->>0); EXIT;
        END IF;
      END LOOP;
    END IF;
    IF why IS NOT NULL THEN
      RAISE NOTICE 'Сверка Алины, сделка %: %, пропуск', did, why;
      CONTINUE;
    END IF;
    FOR c IN SELECT * FROM jsonb_array_elements(p->'cancel') LOOP
      UPDATE fin_ledger SET status = 'cancelled'
       WHERE deal_id = did AND source = 'bitrix' AND status = 'active' AND direction = 'in'
         AND source_ref = format('deal:%s:pay%s', did, c->>0) AND amount = (c->>1)::numeric AND op_date = (c->>2)::date
      RETURNING id INTO rid;
      INSERT INTO audit_log (person_id, action, entity, entity_id, data)
      VALUES (NULL, 'ledger_fix', 'fin_ledger', rid::text,
              jsonb_build_object('deal', did, 'ref', format('deal:%s:pay%s', did, c->>0), 'amount', (c->>1)::numeric,
                                 'op_date', c->>2, 'to', 'cancelled', 'by', 'HEAD 17.11 01:41 UTC «да»: таблица Алины'));
    END LOOP;
    FOR a IN SELECT * FROM jsonb_array_elements(p->'add') LOOP
      ref := CASE WHEN a->>0 IS NULL THEN NULL ELSE format('deal:%s:pay%s', did, a->>0) END;
      day := (a->>1)::date; hist := day < DATE '2026-11-01';
      INSERT INTO fin_ledger (client_uid, op_date, account_code, direction, amount, article_code, period, deal_id, note,
                              source, source_ref, checked_at)
      VALUES (gen_random_uuid(), day, a->>3, 'in', (a->>2)::numeric, 'client_payment', to_char(day, 'YYYY-MM'), did,
              concat_ws(' · ', p->>'title', 'по таблице Алины', CASE WHEN hist THEN 'до ноября' END, nullif(a->>4, ''),
                        CASE WHEN NOT hist THEN 'без чека' END),
              'app', ref, CASE WHEN hist THEN now() END)
      RETURNING id INTO rid;
      INSERT INTO audit_log (person_id, action, entity, entity_id, data)
      VALUES (NULL, 'ledger_fix', 'fin_ledger', rid::text,
              jsonb_build_object('deal', did, 'ref', ref, 'amount', (a->>2)::numeric, 'op_date', a->>1, 'account', a->>3,
                                 'to', 'added', 'by', 'HEAD 17.11 01:41 UTC «да»: таблица Алины'));
    END LOOP;
    SELECT coalesce(sum(CASE WHEN direction = 'in' THEN amount ELSE -amount END), 0) INTO tot FROM fin_ledger
     WHERE deal_id = did AND status = 'active' AND article_code IN ('client_payment', 'design_prepay', 'refund');
    RAISE NOTICE 'Сверка Алины, сделка %: поступило % → %', did, p->>'was', tot;
  END LOOP;
END $$;

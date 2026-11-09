-- HEAD 09.11: «Почему оно улетело в закупку на склад, а не в расходы проекта?» Покупки через «+ Покупка» с № сделки
-- переносим в расходы проекта: object_id = сделка, статья — «Такси / доставка» (только такси) или «Докупка на объект».
-- Суммы, статусы, чеки и строки покупки не меняются; запись в журнал (expense_to_project).
WITH m AS (
  SELECT e.id, e.category AS old_cat,
         CASE WHEN bool_and(l.name ILIKE '%такси%' OR l.name ILIKE '%доставк%') THEN 'transport' ELSE 'purchase' END AS cat
  FROM expenses e JOIN expense_categories c ON c.code = e.category JOIN objects o ON o.id = e.deal_id
  LEFT JOIN stock_lines l ON l.expense_id = e.id
  WHERE c.article IN ('stock', 'canvas') AND e.deal_id IS NOT NULL AND e.object_id = 0
  GROUP BY e.id, e.category
), u AS (
  UPDATE expenses e SET object_id = e.deal_id, category = coalesce(m.cat, 'purchase')
  FROM m WHERE e.id = m.id RETURNING e.id, e.deal_id, e.receipt_file_id, m.old_cat
), f AS (
  UPDATE files SET object_id = u.deal_id FROM u WHERE files.id = u.receipt_file_id AND files.object_id = 0
)
INSERT INTO audit_log (person_id, action, entity, entity_id, data)
SELECT NULL, 'expense_to_project', 'expenses', u.id::text, jsonb_build_object('from', u.old_cat, 'deal', u.deal_id, 'by', 'HEAD 09.11') FROM u;

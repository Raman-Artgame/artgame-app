-- HEAD 14.11: доплата до минимума, пока месяц идёт, — «по итогам месяца» (status pending): не входит в начислено и «осталось».
ALTER TABLE fin_accruals DROP CONSTRAINT IF EXISTS fin_accruals_status_check;
ALTER TABLE fin_accruals ADD CONSTRAINT fin_accruals_status_check CHECK (status IN ('active', 'cancelled', 'pending'));

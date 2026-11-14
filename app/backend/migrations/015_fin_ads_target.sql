-- Таргет в тенге в день (HEAD 06.11): план месяца = fin.var.ads_target_day × дней в месяце.
UPDATE fin_articles SET plan_key = 'fin.var.ads_target_day' WHERE code = 'ads_target';

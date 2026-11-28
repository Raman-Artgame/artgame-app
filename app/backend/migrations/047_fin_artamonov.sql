-- HEAD 11.11.2026: временно, до конца 2026, оплаты клиентов можно вносить на счёт «ИП Артамонов».
-- valid_until — последний день, которым можно датировать новую оплату клиента на этот счёт (NULL — без срока).
-- После срока счёт остаётся в журнале, остатках и витрине; ничего не удаляется. Продлить — поменять дату.
ALTER TABLE fin_accounts ADD COLUMN IF NOT EXISTS valid_until date;
INSERT INTO fin_accounts (code, title, sort, valid_until) VALUES ('artamonov', 'ИП Артамонов', 4, '2026-12-31')
    ON CONFLICT (code) DO NOTHING;

-- Реклама проходит то же утверждение HEAD, что и публикации (HEAD: «утверждаю каждую публикацию и рекламу»): формат «Реклама».
-- В договоре с агентством — 2 рекламные кампании в месяц.
ALTER TABLE mkt_norms DROP CONSTRAINT IF EXISTS mkt_norms_kind_check;
ALTER TABLE mkt_norms ADD CONSTRAINT mkt_norms_kind_check CHECK (kind IN ('reels', 'post', 'stories', 'ad'));
INSERT INTO mkt_norms (kind, title, per_month, sort) VALUES ('ad', 'Рекламные кампании', 2, 4) ON CONFLICT (kind) DO NOTHING;

-- Публикация хранит исходники, монтаж и финал (HEAD 26.11: «чтобы всё качественно выгружалось и было по своим местам»).
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS src_ids bigint[] NOT NULL DEFAULT '{}';     -- исходники из «Медиа»
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS draft_ids bigint[] NOT NULL DEFAULT '{}';   -- монтаж: черновые версии
ALTER TABLE mkt_posts ADD COLUMN IF NOT EXISTS out_saved text;                            -- куда лёг финал после «Утверждаю»
CREATE INDEX IF NOT EXISTS mkt_posts_src ON mkt_posts USING gin (src_ids);
CREATE INDEX IF NOT EXISTS mkt_posts_files ON mkt_posts USING gin (file_ids);

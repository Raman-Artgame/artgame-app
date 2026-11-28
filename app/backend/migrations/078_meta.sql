-- Загрузчик Meta (HEAD 24.11 «Делай загрузчик мета»): расход рекламного кабинета и статистика Instagram — напрямую по токену.
-- Токен живёт только на сервере (META_TOKEN в /etc/artgame-app/<env>.env), в базе и в репозитории его нет.
CREATE TABLE IF NOT EXISTS mkt_meta_day (
    account     text NOT NULL,              -- act_…
    day         date NOT NULL,
    spend       numeric(14,2) NOT NULL DEFAULT 0,
    currency    text,
    impressions bigint NOT NULL DEFAULT 0,
    reach       bigint NOT NULL DEFAULT 0,
    clicks      bigint NOT NULL DEFAULT 0,
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account, day)
);
CREATE TABLE IF NOT EXISTS mkt_ig_day (
    day        date PRIMARY KEY,
    followers  integer,                     -- подписчиков на конец дня (снимок в момент сбора)
    reach      integer,
    views      integer,
    profile_views integer,
    interactions  integer,
    fetched_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mkt_ig_media (
    id         text PRIMARY KEY,
    kind       text,                        -- REELS | FEED | STORY
    media_type text,
    permalink  text,
    caption    text,
    posted_at  timestamptz,
    views      integer,
    reach      integer,
    likes      integer,
    comments   integer,
    saved      integer,
    shares     integer,
    fetched_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mkt_ig_media_posted ON mkt_ig_media (posted_at DESC);

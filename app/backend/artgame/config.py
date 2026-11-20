"""Настройки только из переменных среды. Секретов в репозитории нет."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARTGAME_", env_file=None)

    database_url: str = "postgresql://artgame@localhost/artgame"
    bot_token: str = ""                 # ARTGAME_BOT_TOKEN, только на сервере
    head_tg_id: int = 0                 # Telegram ID HEAD: первый вход получает роль head
    initdata_max_age: int = 24 * 3600   # сек, сколько живёт подпись Telegram
    private_key: str = ""               # ключ шифрования ИИН/реквизитов (pgcrypto)
    env_name: str = "test"              # test | prod
    backfill_from: str = "2026-11-01"   # «Прошлая смена / расход» (HEAD 09.11): с какого дня можно внести задним числом
    backfill_until: str = "2026-11-15"  # и до какого дня включительно открыта кнопка (ARTGAME_BACKFILL_UNTIL)
    public_origin: str = "https://app.artgame.world"
    gateway_url: str = ""              # шлюз ARTGAME (MCP) на localhost, чтение Битрикса через bitrix_read
    gateway_token: str = ""            # если шлюз требует токен
    bitrix_webhook: str = ""           # входящий вебхук Битрикса (права CRM): запись из приложения, решение HEAD 05.11
    pay_push: bool = False             # ARTGAME_PAY_PUSH=1: итоги оплат сделок пишет приложение (deal_money, HEAD 10.11) —
                                       # только в одной среде и только когда робот FIN03 на сервере выключен
    drive_inbox: str = ""              # устарело: чеки без сделки — drive.RECEIPTS_ROOT_ID / drive_receipts
    drive_receipts: str = ""           # запасной ID папки «10 ФИНАНСЫ / Расходы чеки» (если RECEIPTS_ROOT_ID пуст)
    google_sa_file: str = ""            # путь к JSON сервисного аккаунта на сервере
    # Google Таблица-витрина «Финансы 2026 — витрина (из приложения)» (HEAD 06.11): сервер пишет, руками не правим
    fin_sheet_id: str = "1-beqAb-w27ZJnLepsdCZBbxIRQYWSUFDsJMdoBneS-s"
    fin_sheet_year: int = 2026   # год витрины; новый год — новый файл и новый ARTGAME_FIN_SHEET_ID/_YEAR
    anthropic_key: str = ""             # ARTGAME_ANTHROPIC_KEY: ИИ-помощник карточки сделки; пусто — разбор правилами
    content_key: str = ""               # hex 32 байта: расшифровка рабочих мест (places/*.enc)


settings = Settings()

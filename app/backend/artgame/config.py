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
    public_origin: str = "https://app.artgame.world"
    gateway_url: str = ""              # шлюз ARTGAME (MCP) на localhost, чтение Битрикса через bitrix_read
    gateway_token: str = ""            # если шлюз требует токен
    bitrix_webhook: str = ""           # входящий вебхук Битрикса (права CRM): запись из приложения, решение HEAD 05.11
    drive_inbox: str = ""              # папка Диска для чеков «Офис / без объекта»
    google_sa_file: str = ""            # путь к JSON сервисного аккаунта на сервере
    # Google Таблица-витрина «Финансы 2026 — витрина (из приложения)» (HEAD 06.11): сервер пишет, руками не правим
    fin_sheet_id: str = "1-beqAb-w27ZJnLepsdCZBbxIRQYWSUFDsJMdoBneS-s"
    content_key: str = ""               # hex 32 байта: расшифровка рабочих мест (places/*.enc)


settings = Settings()

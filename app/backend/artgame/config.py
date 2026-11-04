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
    bitrix_read_url: str = ""          # входящий вебхук Битрикса только на чтение (crm.deal.list)
    drive_inbox: str = ""              # папка Диска для чеков «Офис / без объекта»
    google_sa_file: str = ""            # путь к JSON сервисного аккаунта на сервере


settings = Settings()

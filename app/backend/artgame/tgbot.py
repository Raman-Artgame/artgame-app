"""Бот @artgame_team_bot: профиль и ответ на «Старт» (HEAD 08.11, запуск команды 09.11).

- `setup()` — при каждой выкладке (install_test.sh): имя, описание до «Старт», короткое описание,
  без списка команд, кнопка меню «ARTGAME», webhook на /api/tg/hook. Меняет только то, что отличается.
- `/api/tg/hook` — Telegram присылает сообщения. Текст от сотрудника — в «Диалог с HEAD» (dm.from_telegram); иначе приветствие
  с кнопкой «Открыть ARTGAME». Подпись — заголовок X-Telegram-Bot-Api-Secret-Token (выводится из токена).
Токен только в env сервера (ARTGAME_BOT_TOKEN).

Запуск вручную на сервере: python -m artgame.tgbot setup
"""
import hashlib
import hmac
import sys

import httpx
from fastapi import APIRouter, Header, Request

from .config import settings

router = APIRouter()

NAME = "ARTGAME"
DESCRIPTION = ("ARTGAME — рабочее приложение команды.\n\n"
               "Смены, проекты, расходы и учёба — в одной кнопке.\n\n"
               "Нажми «Старт», потом «ARTGAME» внизу.")
SHORT = "Приложение команды ARTGAME. Вход — кнопка «ARTGAME» внизу."
MENU_TEXT = "ARTGAME"


def welcome(first_name: str) -> str:
    hi = f"Привет, {first_name}!" if first_name else "Привет!"
    return (f"{hi} Это ARTGAME — рабочее приложение команды.\n\n"
            "Нажми «Открыть ARTGAME» — там твоя смена, проекты, расходы и учёба.\n"
            "Потом заходи кнопкой «ARTGAME» внизу чата.")


def hook_secret() -> str:
    return hashlib.sha256(b"artgame-tg-hook:" + settings.bot_token.encode()).hexdigest()


def app_url() -> str:
    return settings.public_origin.rstrip("/") + "/"


def call(method: str, **params) -> dict:
    r = httpx.post(f"https://api.telegram.org/bot{settings.bot_token}/{method}", json=params, timeout=30)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"{method}: {j.get('description')}")
    return j.get("result")


CALL = call  # тесты подменяют


@router.post("/api/tg/hook")
async def tg_hook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    if not settings.bot_token or not hmac.compare_digest(x_telegram_bot_api_secret_token, hook_secret()):
        return {"ok": False}
    upd = await request.json()
    msg = upd.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") != "private" or not chat.get("id"):
        return {"ok": True}
    try:
        kb = {"inline_keyboard": [[{"text": "Открыть ARTGAME", "web_app": {"url": app_url()}}]]}
        try:   # «Диалог с HEAD» (09.11): сообщение сотрудника → HEAD, ответ HEAD свайпом → сотруднику
            from . import dm
            said = dm.from_telegram(int(chat["id"]), msg.get("text") or msg.get("caption") or "",
                                    (msg.get("reply_to_message") or {}).get("message_id"))
        except Exception as e:
            print("tg_hook dm:", e, file=sys.stderr)
            said = None
        if said:
            CALL("sendMessage", chat_id=chat["id"], text=said, reply_markup=kb)
            return {"ok": True}
        text = welcome((msg.get("from") or {}).get("first_name", ""))
        try:   # баннер «Добро пожаловать» (frontend/public/bot-welcome.jpg); не вышло — просто текст
            CALL("sendPhoto", chat_id=chat["id"], photo=app_url() + "bot-welcome.jpg", caption=text, reply_markup=kb)
        except Exception as e:
            print("tg_hook photo:", e, file=sys.stderr)
            CALL("sendMessage", chat_id=chat["id"], text=text, reply_markup=kb)
    except Exception as e:   # Telegram не должен получать 500 и повторять
        print("tg_hook:", e, file=sys.stderr)
    return {"ok": True}


def setup() -> list[str]:
    """Привести профиль бота к нужному виду. Возвращает, что изменено (для лога выкладки)."""
    done = []
    if (CALL("getMyName") or {}).get("name") != NAME:
        CALL("setMyName", name=NAME); done.append("имя")
    if (CALL("getMyDescription") or {}).get("description") != DESCRIPTION:
        CALL("setMyDescription", description=DESCRIPTION); done.append("описание")
    if (CALL("getMyShortDescription") or {}).get("short_description") != SHORT:
        CALL("setMyShortDescription", short_description=SHORT); done.append("короткое описание")
    if CALL("getMyCommands"):
        CALL("deleteMyCommands"); done.append("команды убраны")
    menu = CALL("getChatMenuButton") or {}
    if menu.get("type") != "web_app" or menu.get("text") != MENU_TEXT or (menu.get("web_app") or {}).get("url") != app_url():
        CALL("setChatMenuButton", menu_button={"type": "web_app", "text": MENU_TEXT, "web_app": {"url": app_url()}})
        done.append("кнопка меню")
    hook = settings.public_origin.rstrip("/") + "/api/tg/hook"
    info = CALL("getWebhookInfo") or {}
    old = info.get("url") or ""
    # всегда ставим заново (секрет зависит от токена), старые сообщения сбрасываем только при смене адреса
    CALL("setWebhook", url=hook, secret_token=hook_secret(), allowed_updates=["message"], drop_pending_updates=old != hook)
    if old != hook:
        done.append(f"webhook (был: {old.split('/')[2] if '://' in old else 'нет'})")
    if info.get("last_error_message"):
        done.append(f"прошлая ошибка webhook: {info['last_error_message']}")
    return done


if __name__ == "__main__":
    if sys.argv[1:] != ["setup"]:
        sys.exit("python -m artgame.tgbot setup")
    if not settings.bot_token:
        sys.exit("ARTGAME_BOT_TOKEN не задан")
    try:
        ch = setup()
    except Exception as e:   # без трассировки: лог выкладки виден в GitHub
        sys.exit(f"бот: ошибка {type(e).__name__}: {str(e).replace(settings.bot_token, '***')}")
    print("бот:", ", ".join(ch) if ch else "уже в порядке")

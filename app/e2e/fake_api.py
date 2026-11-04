"""API для сквозного теста: Google Диск подменён, чек «сохраняется» по выдуманной ссылке."""
import uvicorn

from artgame import drive
from artgame.main import app

drive.save_photo = lambda conn, obj, name, data: f"https://drive.example/{obj['id']}/{len(data)}"

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8100)

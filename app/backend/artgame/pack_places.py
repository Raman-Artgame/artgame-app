"""Упаковка рабочего места в зашифрованные файлы для публичного репозитория.

    ARTGAME_CONTENT_KEY=<hex> python -m artgame.pack_places <папка_с_index.html> <код места>

Старые .enc этого места заменяются целиком (история — в git). Ключ — тот же, что в env сервера.
"""
import os
import shutil
import sys
from pathlib import Path

from .places import PLACES, ROOT, encrypt


def pack(src: Path, code: str, key: str) -> int:
    if code not in PLACES:
        raise SystemExit(f"неизвестное место {code}")
    if not (src / "index.html").is_file():
        raise SystemExit("нет index.html")
    dst = ROOT / code
    if dst.exists():
        shutil.rmtree(dst)
    n = 0
    for f in sorted(src.rglob("*")):
        if f.is_file():
            rel = f.relative_to(src).as_posix()
            out = dst / (rel + ".enc")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(encrypt(f.read_bytes(), f"{code}/{rel}", key))
            n += 1
    ROOT.mkdir(exist_ok=True)
    (ROOT / "_check.enc").write_bytes(encrypt(b"ok", "_check", key))
    return n


if __name__ == "__main__":
    key = os.environ.get("ARTGAME_CONTENT_KEY", "")
    if len(bytes.fromhex(key)) != 32:
        raise SystemExit("нужен ARTGAME_CONTENT_KEY (hex, 32 байта)")
    print(pack(Path(sys.argv[1]), sys.argv[2], key), "файлов")

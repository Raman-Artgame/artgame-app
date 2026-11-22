"""Миниатюра картинки отдельным процессом: python -m artgame.thumb_worker <файл> <куда.jpg>.

HEAD 22.11: PNG эскизов «@100x» — 470 млн точек; Диск превью не строит, обычная библиотека на таком требует 2 ГБ памяти.
libvips читает картинку полосами (≈200 МБ и 3 с на 470 млн точек). Отдельный процесс — чтобы память вернулась сразу
и сбой на битом файле не задел приложение. Нет libvips — запасной путь через Pillow для небольших картинок."""
import os
import sys

MAX_PIXELS = 2_000_000_000
PIL_MAX_PIXELS = 60_000_000
SIDE = 480


def make(src: str, dst: str) -> None:
    try:
        os.environ.setdefault("VIPS_CONCURRENCY", "1")
        import pyvips
    except Exception:  # noqa: BLE001
        pyvips = None
    if pyvips:
        head = pyvips.Image.new_from_file(src)
        if head.width * head.height > MAX_PIXELS:
            raise SystemExit(f"too big: {head.width}x{head.height}")
        im = pyvips.Image.thumbnail(src, SIDE, height=SIDE)
        if im.hasalpha():   # прозрачный фон — на белый, как у миниатюр Диска
            im = im.flatten(background=[255, 255, 255])
        im.jpegsave(dst, Q=82)
        return
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = PIL_MAX_PIXELS
    im = Image.open(src)
    if im.width * im.height > PIL_MAX_PIXELS:
        raise SystemExit(f"too big for pillow: {im.width}x{im.height}")
    im.thumbnail((SIDE, SIDE))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    im.convert("RGB").save(dst, "JPEG", quality=82)


if __name__ == "__main__":
    make(sys.argv[1], sys.argv[2])

"""Монтаж ролика «МОП за минуту»: 1080×1920, 30 fps. Тёмный фон бренда, телефон с записью, главы, анимация текста, своя музыка."""
import subprocess, json, glob, math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

D = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(D, '..', 'r')
A = glob.glob(R + '/a/*.webm')[0]; B = glob.glob(R + '/b/*.webm')[0]
F8 = os.path.join(D, '..', 'onest800.ttf'); F5 = os.path.join(D, '..', 'onest500.ttf')
W, H, FPS = 1080, 1920, 30
INK, PAPER, RED, GREY = (11, 11, 13), (241, 240, 236), (230, 0, 65), (156, 151, 160)
PW, PH = 620, 1240                     # экран телефона
PX, PY = (W - PW) // 2, 600

INTRO, OUTRO = 2.6, 3.6
SCENES = [  # (видео, с, по, скорость, заголовок, подпись)
    (A, 1.0, 9.0, 2.0, 'Зарегистрируйтесь', 'Имя и телефон — HEAD откроет доступ'),
    (B, 0.5, 9.5, 1.6, 'Начинайте день здесь', '«Горит» → «Сегодня» → «Можно позже»'),
    (B, 10.5, 26.0, 2.2, 'Лид → сделка', 'Город, услуга, площадь — без них не пустит'),
    (B, 26.5, 33.5, 1.6, 'Карточка сделки', 'Шаги сверху, красная кнопка — следующий шаг'),
    (B, 33.5, 43.0, 1.9, 'Цена и срок — сами', 'Расчёт по ценам компании, в Битрикс одной кнопкой'),
    (B, 43.4, 46.8, 0.9, 'Не заполнено — дальше нельзя', 'Замок показывает, чего не хватает'),
    (B, 47.5, 56.0, 1.7, 'Вставьте переписку', 'Помощник заполнит поля сам, вы проверяете'),
    (B, 56.0, 76.0, 3.0, 'КП и договор — в карточке', 'Скачали файл — он уже в сделке Битрикса'),
    (B, 76.5, 83.0, 1.6, 'После звонка — итог', 'Перезвон: задача в Битриксе и напоминание бота'),
    (B, 83.0, 89.5, 1.6, 'Отказ — только с причиной', '8 причин из списка + слова клиента'),
    (B, 89.5, 100.0, 2.2, 'Проекты и ваш месяц', 'Кто где работает · план 2/7/15 млн · траты с чеком'),
]
DUR = [(e - s) / sp for _, s, e, sp, *_ in SCENES]
T = [INTRO]
for d in DUR: T.append(T[-1] + d)
TOTAL = T[-1] + OUTRO
N = int(round(TOTAL * FPS))

def font(f, s): return ImageFont.truetype(f, s)
def ease(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def ease_io(x): x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)

def text_layer(lines, width=W - 160):
    """lines: [(text, font, color, gap_after)] → RGBA, перенос по словам."""
    rows = []
    d = ImageDraw.Draw(Image.new('L', (1, 1)))
    for txt, f, col, gap in lines:
        words, cur = txt.split(), ''
        for w_ in words:
            nxt = (cur + ' ' + w_).strip()
            if d.textlength(nxt, font=f) > width and cur:
                rows.append((cur, f, col, 0)); cur = w_
            else: cur = nxt
        rows.append((cur, f, col, gap))
    h = sum(f.size * 1.12 + g for _, f, _, g in rows)
    im = Image.new('RGBA', (width, int(h) + 10), (0, 0, 0, 0)); dr = ImageDraw.Draw(im); y = 0
    for t, f, col, g in rows:
        dr.text((0, y), t, font=f, fill=col); y += f.size * 1.12 + g
    return im

def with_alpha(im, a):
    if a >= 0.999: return im
    r, g, b, al = im.split(); al = al.point(lambda v: int(v * a)); return Image.merge('RGBA', (r, g, b, al))

# ---------- статичные слои ----------
yy, xx = np.mgrid[0:H, 0:W]
bg = np.zeros((H, W, 3), np.float32) + np.array(INK, np.float32)
grid = ((xx % 60 == 0) | (yy % 60 == 0)).astype(np.float32) * 6
bg += grid[..., None]
BG = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8))
gs = 900; gy, gx = np.mgrid[0:gs, 0:gs]
g = np.exp(-(((gx - gs / 2) ** 2 + (gy - gs / 2) ** 2) / (2 * (gs / 5) ** 2)))
GLOW = Image.fromarray(np.dstack([np.full((gs, gs), RED[0]), np.full((gs, gs), RED[1]), np.full((gs, gs), RED[2]), (g * 120)]).astype(np.uint8), 'RGBA')

R_ = 64; BZ = 16
mask = Image.new('L', (PW, PH), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, PW - 1, PH - 1), R_ - BZ, fill=255)
frame = Image.new('RGBA', (PW + 2 * BZ, PH + 2 * BZ), (0, 0, 0, 0))
ImageDraw.Draw(frame).rounded_rectangle((0, 0, PW + 2 * BZ - 1, PH + 2 * BZ - 1), R_, fill=(26, 24, 28, 255), outline=(60, 56, 64, 255), width=3)
sh = Image.new('RGBA', (PW + 200, PH + 200), (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle((70, 90, PW + 130, PH + 150), R_, fill=(0, 0, 0, 200)); SHADOW = sh.filter(ImageFilter.GaussianBlur(36))
RIM = Image.new('RGBA', (PW + 160, PH + 160), (0, 0, 0, 0))
ImageDraw.Draw(RIM).rounded_rectangle((40, 40, PW + 120, PH + 120), R_ + 10, outline=RED + (90,), width=4); RIM = RIM.filter(ImageFilter.GaussianBlur(10))

f_title, f_sub, f_num = font(F8, 76), font(F5, 38), font(F8, 30)
TXT = []
for i, (*_, title, sub) in enumerate(SCENES):
    TXT.append((text_layer([(f'{i + 1:02d} / {len(SCENES):02d}', f_num, RED + (255,), 18)]),
                text_layer([(title, f_title, PAPER + (255,), 14)]), text_layer([(sub, f_sub, GREY + (255,), 0)])))
INTRO_L = [text_layer([('ARTGAME', font(F8, 34), RED + (255,), 0)]), text_layer([('Приложение', font(F8, 120), PAPER + (255,), 0)]),
           text_layer([('для МОП', font(F8, 120), PAPER + (255,), 0)]), text_layer([('за одну минуту', font(F5, 52), GREY + (255,), 0)])]
OUT_L = [text_layer([('Запомнить', font(F8, 34), RED + (255,), 0)])] + \
        [text_layer([(t, font(F8, 64), PAPER + (255,), 0)], W - 240) for t in ('Работа — в приложении', 'Битрикс заполняется сам', 'Не заполнено — дальше нельзя')] + \
        [text_layer([('Вопросы — к HEAD', font(F5, 44), GREY + (255,), 0)])]

# ---------- кадры сцен ----------
def clip_frames(src, s, e, sp):
    n = int(round((e - s) / sp * FPS))
    cmd = ['ffmpeg', '-v', 'error', '-ss', str(s), '-t', str(e - s), '-i', src, '-vf',
           f'crop=390:780:0:0,setpts=PTS/{sp},fps={FPS},scale={PW}:{PH}:flags=lanczos,unsharp=5:5:0.6', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    fr = [Image.frombytes('RGB', (PW, PH), raw[i * PW * PH * 3:(i + 1) * PW * PH * 3]) for i in range(len(raw) // (PW * PH * 3))]
    while len(fr) < n: fr.append(fr[-1])
    return fr[:n]

print('кадры сцен…', flush=True)
CLIPS = [clip_frames(src, s, e, sp) for src, s, e, sp, *_ in SCENES]

def phone(img, scale, dy, alpha=1.0):
    """Телефон с экраном img: масштаб, сдвиг по y."""
    sw, sh_ = int((PW + 2 * BZ) * scale), int((PH + 2 * BZ) * scale)
    layer = Image.new('RGBA', (PW + 2 * BZ, PH + 2 * BZ), (0, 0, 0, 0))
    layer.alpha_composite(frame)
    scr = img.convert('RGBA'); scr.putalpha(mask); layer.alpha_composite(scr, (BZ, BZ))
    if scale != 1.0: layer = layer.resize((sw, sh_), Image.BICUBIC)
    return with_alpha(layer, alpha), (W - sw) // 2, PY - BZ + dy - (sh_ - (PH + 2 * BZ)) // 2

enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', os.path.join(D, 'video.mp4')], stdin=subprocess.PIPE)
for k in range(N):
    t = k / FPS
    im = BG.copy().convert('RGBA')
    gx_ = int(W / 2 - gs / 2 + 260 * math.sin(t * 0.5)); gy_ = int(380 - gs / 2 + 120 * math.cos(t * 0.37))
    im.alpha_composite(GLOW, (gx_, gy_)); im.alpha_composite(GLOW, (int(-gs / 2 + 120 + 80 * math.cos(t * .4)), int(H - 500 + 90 * math.sin(t * .3))))
    if t < INTRO:   # заставка
        a = [ease((t - d0) / 0.45) for d0 in (0.0, 0.15, 0.3, 0.55)]
        ys = [520, 600, 740, 900]
        for L, y, aa in zip(INTRO_L, ys, a):
            im.alpha_composite(with_alpha(L, aa), (90, int(y + 60 * (1 - aa))))
        wl = int((W - 180) * ease((t - 0.7) / 0.6)); ImageDraw.Draw(im).rectangle((90, 1000, 90 + wl, 1012), fill=RED + (255,))
        if t > INTRO - 0.35:  # уход вверх
            o = ease((t - (INTRO - 0.35)) / 0.35); im = Image.blend(im, BG.convert('RGBA'), o)
    elif t < T[-1]:
        i = max(j for j in range(len(SCENES)) if T[j] <= t); lt = t - T[i]; d = DUR[i]
        fi = min(int(lt * FPS), len(CLIPS[i]) - 1); img = CLIPS[i][fi]
        if lt < 0.22 and i > 0:   # перетекание кадров между сценами
            img = Image.blend(CLIPS[i - 1][-1], img, ease_io(lt / 0.22))
        enter = ease((t - INTRO) / 0.6)                      # телефон въезжает снизу в первой сцене
        punch = 1.0 + 0.025 * ease_io(lt / d) + (0.03 * (1 - ease(lt / 0.25)) if i > 0 else 0)   # лёгкий «наезд» и толчок на склейке
        ph, x, y = phone(img, punch, int(900 * (1 - enter)))
        im.alpha_composite(SHADOW, (x - 100 + int((ph.width - PW - 2 * BZ) / 2), y - 100))
        im.alpha_composite(RIM, (x - 40 - BZ + int((ph.width - PW - 2 * BZ) / 2), y - 40 - BZ))
        im.alpha_composite(ph, (x, y))
        # текст главы: выезд снизу, у ухода — гаснет
        num, tit, sub = TXT[i]
        ain = [ease((lt - d0) / 0.35) for d0 in (0.0, 0.06, 0.16)]
        aout = 1 - ease((lt - (d - 0.18)) / 0.18) if i < len(SCENES) - 1 else 1 - ease((lt - (d - 0.3)) / 0.3)
        y0 = 150
        im.alpha_composite(with_alpha(num, ain[0] * aout), (80, int(y0 + 40 * (1 - ain[0]))))
        im.alpha_composite(with_alpha(tit, ain[1] * aout), (80, int(y0 + 56 + 50 * (1 - ain[1]))))
        im.alpha_composite(with_alpha(sub, ain[2] * aout), (80, int(y0 + 64 + tit.height + 40 * (1 - ain[2]))))
        # прогресс глав
        dr = ImageDraw.Draw(im); seg = (W - 160 - (len(SCENES) - 1) * 8) / len(SCENES)
        for j in range(len(SCENES)):
            x0 = 80 + j * (seg + 8); dr.rounded_rectangle((x0, 84, x0 + seg, 92), 4, fill=(42, 37, 48, 255))
            fill = 1.0 if j < i else (lt / d if j == i else 0)
            if fill > 0: dr.rounded_rectangle((x0, 84, x0 + seg * fill, 92), 4, fill=RED + (255,))
        # вспышка-шторка на склейке
        if lt < 0.12 and i > 0:
            wx = int(W * ease(lt / 0.12)); dr.rectangle((0, 0, wx, 12), fill=RED + (255,))
    else:   # финал
        lt = t - T[-1]
        a = [ease((lt - d0) / 0.4) for d0 in (0.0, 0.2, 0.45, 0.7, 1.1)]
        ys = [560, 640, 780, 920, 1120]
        for j, (L, y, aa) in enumerate(zip(OUT_L, ys, a)):
            if 1 <= j <= 3:
                ImageDraw.Draw(im).ellipse((90, y + 22, 90 + 26, y + 48), fill=RED + (int(255 * aa),))
                im.alpha_composite(with_alpha(L, aa), (140, int(y + 30 * (1 - aa))))
            else:
                im.alpha_composite(with_alpha(L, aa), (90, int(y + 30 * (1 - aa))))
        if lt > OUTRO - 0.6: im = Image.blend(im, Image.new('RGBA', (W, H), INK + (255,)), ease((lt - (OUTRO - 0.6)) / 0.6))
    enc.stdin.write(im.convert('RGB').tobytes())
    if k % 300 == 0: print(k, '/', N, flush=True)
enc.stdin.close(); enc.wait()
json.dump({'total': TOTAL, 'cuts': T[1:-1] + [T[-1]], 'intro': INTRO, 'outro': OUTRO, 'out': os.path.join(D, 'music.wav')}, open(os.path.join(D, 'plan.json'), 'w'))
print('готово', TOTAL)

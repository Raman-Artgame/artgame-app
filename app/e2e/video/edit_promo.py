"""Презентационный ролик приложения для компьютера: 1920×1080, 30 fps, озвучка, субтитры, музыка, геймификация.
python edit_promo.py <папка записей ролей> <папка озвучки> <папка картинок> <выход.mp4>"""
import json, math, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
import music  # noqa: E402

REC, VO, IMG, OUTF = sys.argv[1:5]
P = json.load(open(os.path.join(D, 'promo.json'))); SC = P['scenes']
DUR = json.load(open(f'{VO}/durations.json'))['promo']
FD = '/usr/share/fonts/opentype/inter/'
F = lambda w, s: ImageFont.truetype(FD + {'b': 'InterDisplay-ExtraBold.otf', 'k': 'InterDisplay-Black.otf', 's': 'Inter-SemiBold.otf', 'm': 'Inter-Medium.otf'}[w], s)
W, H, FPS = 1920, 1080, 30
INK, PAPER, RED, GREY, OK, WARN = (11, 9, 10), (245, 239, 241), (230, 0, 65), (168, 152, 158), (61, 220, 132), (255, 176, 32)
INTRO, OUTRO, LEAD = 3.2, 4.2, 0.35
plan, t = [], INTRO
for i, d in enumerate(DUR):
    plan.append(dict(i=i, t=t, d=d + LEAD + 0.75)); t += plan[-1]['d']
TOTAL = t + OUTRO; N = int(round(TOTAL * FPS))

def ease(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def eio(x): x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)
def back(x):
    x = max(0.0, min(1.0, x)); c = 1.7; return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2

def wrap(txt, f, width):
    d = ImageDraw.Draw(Image.new('L', (1, 1))); rows, cur = [], ''
    for w_ in txt.split():
        n = (cur + ' ' + w_).strip()
        if d.textlength(n, font=f) > width and cur: rows.append(cur); cur = w_
        else: cur = n
    return rows + [cur]

def T(txt, f, col, width=1000, lh=1.1):
    rows = wrap(txt, f, width)
    im = Image.new('RGBA', (width, int(len(rows) * f.size * lh) + 14), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
    for k, r in enumerate(rows): dr.text((0, k * f.size * lh), r, font=f, fill=col)
    return im

def A(im, a):
    if a >= .999: return im
    if a <= 0: return Image.new('RGBA', im.size, (0, 0, 0, 0))
    r, g, b, al = im.split(); return Image.merge('RGBA', (r, g, b, al.point(lambda v: int(v * a))))

def cover(path, w, h):
    im = Image.open(path).convert('RGB'); s = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2; return im.crop((x, y, x + w, y + h))

# ---------- фон ----------
yy, xx = np.mgrid[0:H, 0:W]
bg = np.zeros((H, W, 3), np.float32) + np.array(INK, np.float32)
bg += (((xx % 64) == 0) | ((yy % 64) == 0))[..., None] * 6.0
BG = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert('RGBA')
gs = 1100; gy, gx = np.mgrid[0:gs, 0:gs]
g = np.exp(-(((gx - gs / 2) ** 2 + (gy - gs / 2) ** 2) / (2 * (gs / 5.5) ** 2)))
GLOW = Image.fromarray(np.dstack([np.full((gs, gs), c) for c in RED] + [g * 100]).astype(np.uint8), 'RGBA')
LOGO = Image.open(f'{IMG}/logo_dark.png').convert('RGBA')
LOGO_L = LOGO.resize((720, int(LOGO.height * 720 / LOGO.width)), Image.LANCZOS)
LOGO_S = LOGO.resize((230, int(LOGO.height * 230 / LOGO.width)), Image.LANCZOS)
CH = {k: Image.open(f'{IMG}/{k}.png').convert('RGBA') for k in ('ch_artist', 'ch_cur', 'ch_prod', 'ch_sales', 'ch_design', 'ch_mgmt')}

# левая колонка: глава, заголовок, подпись
f_t, f_s, f_b, f_sub, f_n = F('k', 84), F('m', 34), F('s', 34), F('b', 36), F('s', 26)
HL = [(T(f'{k + 1:02d}', F('k', 30), RED + (255,), 200), T(sc['t'], f_t, PAPER + (255,), 860, 1.02), T(sc['s'], f_s, GREY + (255,), 860)) for k, sc in enumerate(SC)]

# субтитры
def chunks(txt):
    out = []
    for sent in re.split(r'(?<=[.!?])\s+', txt.strip()):
        if len(wrap(sent, f_sub, 1500)) <= 2: out.append(sent); continue
        cur = ''
        for pt in re.split(r'(?<=[,:—])\s+', sent):
            n = (cur + ' ' + pt).strip()
            if len(wrap(n, f_sub, 1500)) > 2 and cur: out.append(cur); cur = pt
            else: cur = n
        if cur: out.append(cur)
    return out
SUBS = []
for p_ in plan:
    cs = chunks(SC[p_['i']]['say']); tot = sum(map(len, cs)); t0 = p_['t'] + LEAD
    for c in cs:
        d = DUR[p_['i']] * len(c) / tot; rows = wrap(c, f_sub, 1500); lh = int(f_sub.size * 1.25)
        im = Image.new('RGBA', (1600, len(rows) * lh + 34), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
        tw = max(dr.textlength(r, font=f_sub) for r in rows)
        dr.rounded_rectangle(((1600 - tw) / 2 - 30, 0, (1600 + tw) / 2 + 30, im.height - 1), 22, fill=(0, 0, 0, 170))
        for k, r in enumerate(rows): dr.text(((1600 - dr.textlength(r, font=f_sub)) / 2, 15 + k * lh), r, font=f_sub, fill=PAPER + (255,))
        SUBS.append((t0, t0 + d, im)); t0 += d

# ---------- телефон с записью роли ----------
PW, PH, BZ, RAD = 380, 760, 12, 44
pmask = Image.new('L', (PW, PH), 0); ImageDraw.Draw(pmask).rounded_rectangle((0, 0, PW - 1, PH - 1), RAD - BZ, fill=255)
PFRAME = Image.new('RGBA', (PW + 2 * BZ, PH + 2 * BZ), (0, 0, 0, 0))
ImageDraw.Draw(PFRAME).rounded_rectangle((0, 0, PW + 2 * BZ - 1, PH + 2 * BZ - 1), RAD, fill=(24, 20, 23, 255), outline=(70, 60, 66, 255), width=3)
sh = Image.new('RGBA', (PW + 200, PH + 200), (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle((70, 90, PW + 130, PH + 150), RAD, fill=(0, 0, 0, 220))
PSHADOW = sh.filter(ImageFilter.GaussianBlur(34))

def clip_frames(role, a, b, d):
    m = json.load(open(f'{REC}/{role}/marks.json')); s, e = m[a][0] + 0.3, m[b][1]
    sp = max(0.7, (e - s) / d); n = int(round(d * FPS))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{s:.3f}', '-t', f'{e - s:.3f}', '-i', f'{REC}/{role}/screen.mp4', '-vf',
                          f'setpts=PTS/{sp:.4f},fps={FPS},scale={PW}:{PH}:flags=lanczos,unsharp=5:5:0.5', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True, check=True).stdout
    sz = PW * PH * 3; fr = [raw[k * sz:(k + 1) * sz] for k in range(len(raw) // sz)] or [bytes(sz)]
    while len(fr) < n: fr.append(fr[-1])
    return fr[:n]

def phone(buf):
    scr = Image.frombytes('RGB', (PW, PH), buf).convert('RGBA'); scr.putalpha(pmask)
    lay = PFRAME.copy(); lay.alpha_composite(scr, (BZ, BZ)); return lay

# ---------- сцены ----------
HERO = cover(f'{IMG}/team.jpg', W, H).convert('RGBA')
grad = Image.new('L', (W, H)); gd = np.clip(1.35 - np.linspace(0, 1.2, W), 0.55, 1)[None, :].repeat(H, 0)
HERO_SHADE = Image.merge('RGBA', [Image.new('L', (W, H), c) for c in INK] + [Image.fromarray((gd * 248).astype(np.uint8))])
STATS = [('30+', 'человек в команде'), ('20+', 'городов с работами'), ('210+', 'проектов в год'), ('10+', 'лет на рынке')]

ROLES = [('ch_artist', 'Роспись', 'Саппорт · Художник'), ('ch_cur', 'Ведут объект', 'Главный · Про'), ('ch_prod', 'Печать', 'Оператор · Мастер'),
         ('ch_sales', 'Продажи', 'МОП · VIP МОП'), ('ch_design', 'Дизайн', 'Главный · Помощник'), ('ch_mgmt', 'HEAD', 'Пульт и финансы')]
ROLE_L = []
for ch, a, b_ in ROLES:
    c = CH[ch]; c = c.resize((230, int(c.height * 230 / c.width)), Image.LANCZOS)
    card = Image.new('RGBA', (270, 420), (0, 0, 0, 0)); dr = ImageDraw.Draw(card)
    dr.rounded_rectangle((0, 0, 269, 419), 20, fill=(21, 17, 19, 255), outline=(46, 37, 41, 255), width=2)
    card.alpha_composite(c, (20, 18)); dr.text((22, 318), a, font=F('b', 32), fill=PAPER); dr.text((22, 362), b_, font=F('m', 22), fill=GREY)
    ROLE_L.append(card)

NODES = [('Битрикс', 'сделки, клиенты, стадии'), ('Google Диск', 'фото, чеки, эскизы'), ('«Значения»', 'цены, ставки, нормы'),
         ('Бот Telegram', 'вход и уведомления'), ('База', 'всё записано, ничего не теряется')]
FEED = [('Смена принята', '+100 опыта', OK), ('5 м² «Сложного»', '= 20 м² «Лёгкого»', PAPER), ('Дизайн утверждён', '+200 опыта', OK),
        ('Сделка оплачена', '+100 за 100 000 ₸', OK), ('Рилс принят', '+30 опыта', OK), ('Переделка', '0 опыта', RED)]
RANKS = [('Той', 'старт: саппорт, оператор'), ('Райтер', 'от 3 000 · художник'), ('Мастер', 'от 10 000 · главный, мастер'),
         ('Кинг', 'от 25 000 · Про'), ('Легенда', 'от 50 000 · только заработать')]
LAYERS = [('Личный путь', 'Ранг, шкала и навыки: быстрее и чище — видно в цифрах'), ('Карта открытий', 'Города, фасады, печать, холсты — открываются делом'),
          ('Общая игра', 'Одна цель сезона на все роли, общий приз'), ('Скины', 'Облик персонажа за баллоны и тайники')]
BADGES = [('Х', 'Сложный'), ('↑', 'Высотник'), ('0', 'Без переделок'), ('Н', 'Наставник'), ('30', '30 минут'), ('XL', 'Огромный')]

def left_text(im, i, lt, d, y0=200, x0=120):
    num, tit, sub = HL[i]; aout = 1 - ease((lt - (d - .25)) / .25)
    a = [ease((lt - k) / .45) for k in (0, .08, .2)]
    im.alpha_composite(A(num, a[0] * aout), (x0, int(y0 + 30 * (1 - a[0]))))
    im.alpha_composite(A(tit, a[1] * aout), (x0, int(y0 + 44 + 50 * (1 - a[1]))))
    im.alpha_composite(A(sub, a[2] * aout), (x0, int(y0 + 58 + tit.height + 40 * (1 - a[2]))))
    return y0 + 80 + tit.height + sub.height, aout

def draw_scene(im, i, lt, d, t):
    sc = SC[i]; k = sc['kind']; dr = ImageDraw.Draw(im)
    if k == 'hero':
        z = 1.06 + .05 * lt / d; hz = HERO.resize((int(W * z), int(H * z)), Image.BILINEAR)
        a = ease(lt / .8) * (1 - ease((lt - (d - .3)) / .3))
        im.alpha_composite(A(hz.crop((int((hz.width - W) * .3), int((hz.height - H) / 2), int((hz.width - W) * .3) + W, int((hz.height - H) / 2) + H)), a))
        im.alpha_composite(A(HERO_SHADE, a))
        y, aout = left_text(im, i, lt, d, 220)
        for j, (n, l) in enumerate(STATS):
            aa = back((lt - 1.2 - j * .35) / .5) * aout; x = 120 + j * 300
            if aa > 0:
                im.alpha_composite(A(T(n, F('k', 92), RED + (255,), 300), min(1, aa)), (x, int(y + 70 + 30 * (1 - min(1, aa)))))
                im.alpha_composite(A(T(l, F('m', 26), PAPER + (255,), 260), min(1, aa)), (x, y + 180))
    elif k == 'roles':
        y, aout = left_text(im, i, lt, d, 110)
        for j, c in enumerate(ROLE_L):
            aa = back((lt - .5 - j * .22) / .55); x = 120 + j * 290; yy_ = 470 + int(80 * (1 - min(1, aa))) + int(8 * math.sin(t * 1.6 + j))
            if aa > 0: im.alpha_composite(A(c, min(1, aa) * aout), (x, yy_))
    elif k == 'clip':
        y, aout = left_text(im, i, lt, d, 230)
        for j, b_ in enumerate(sc['b']):
            aa = ease((lt - 1.0 - j * .9) / .45) * aout
            if aa <= 0: continue
            yb = y + 50 + j * 78
            dr.rounded_rectangle((120, yb + 10, 140, yb + 30), 6, fill=RED + (int(255 * aa),))
            im.alpha_composite(A(T(b_, f_b, PAPER + (255,), 760), aa), (int(166 - 30 * (1 - aa)), yb))
        fr = CLIPS[i]; buf = fr[min(int(lt * FPS), len(fr) - 1)]
        ph = phone(buf); en = ease(lt / .6) * aout
        x = 1330 + int(300 * (1 - ease(lt / .6))); yph = (H - ph.height) // 2 - 60 + int(6 * math.sin(t * 1.2))
        im.alpha_composite(A(PSHADOW, en), (x - 80, yph - 80)); im.alpha_composite(A(ph, en), (x, yph))
    elif k == 'links':
        y, aout = left_text(im, i, lt, d, 180)
        cx, cy, rr = 1330, 560, 330
        hub = ease((lt - .3) / .5) * aout
        for j, (n, l) in enumerate(NODES):
            ang = -math.pi / 2 + j * 2 * math.pi / len(NODES) + .05 * math.sin(t * .4)
            nx, ny = cx + rr * math.cos(ang), cy + rr * .82 * math.sin(ang)
            aa = ease((lt - .8 - j * .35) / .5) * aout
            if aa <= 0: continue
            dr.line((cx, cy, nx, ny), fill=(90, 30, 50, int(255 * aa)), width=3)
            for q in range(3):   # бегущие точки по связи
                f_ = ((t * .45 + q / 3 + j * .13) % 1); px, py = cx + (nx - cx) * f_, cy + (ny - cy) * f_
                dr.ellipse((px - 6, py - 6, px + 6, py + 6), fill=RED + (int(255 * aa),))
            box = Image.new('RGBA', (300, 96), (0, 0, 0, 0)); bd = ImageDraw.Draw(box)
            bd.rounded_rectangle((0, 0, 299, 95), 18, fill=(21, 17, 19, 255), outline=(70, 50, 58, 255), width=2)
            bd.text((20, 14), n, font=F('b', 30), fill=PAPER); bd.text((20, 56), l, font=F('m', 20), fill=GREY)
            im.alpha_composite(A(box, aa), (int(nx - 150), int(ny - 48)))
        if hub > 0:
            r_ = 120 * back((lt - .3) / .5) + 6 * math.sin(t * 2)
            dr.ellipse((cx - r_, cy - r_, cx + r_, cy + r_), fill=RED + (int(255 * hub),))
            for line_, yo in (('ПРИЛОЖЕНИЕ', -22), ('ARTGAME', 18)):
                ff = F('k', 30); tw = dr.textlength(line_, font=ff); dr.text((cx - tw / 2, cy + yo - 16), line_, font=ff, fill=(255, 255, 255, int(255 * hub)))
    elif k == 'game':
        y, aout = left_text(im, i, lt, d, 170)
        for j, (a_, b_, col) in enumerate(FEED):
            aa = ease((lt - .8 - j * 1.1) / .4) * aout
            if aa <= 0: continue
            yb = 160 + j * 118; x = 1100 + int(120 * (1 - aa))
            box = Image.new('RGBA', (680, 98), (0, 0, 0, 0)); bd = ImageDraw.Draw(box)
            bd.rounded_rectangle((0, 0, 679, 97), 18, fill=(21, 17, 19, 255), outline=col + (160,), width=2)
            bd.text((26, 28), a_, font=F('b', 32), fill=PAPER); tw = bd.textlength(b_, font=F('k', 30)); bd.text((654 - tw, 30), b_, font=F('k', 30), fill=col)
            im.alpha_composite(A(box, aa), (x, yb))
        xp = int(100 * min(6, max(0, (lt - .8) / 1.1))) if lt > .8 else 0
        cards = [('ОПЫТ', 'навсегда, даёт ранг'), ('БАЛЛОНЫ', 'валюта на скины'), ('ДЕНЬГИ', 'только по «Значениям»')]
        for j, (a_, b_) in enumerate(cards):
            aa = ease((lt - 2.5 - j * .6) / .5) * aout
            if aa <= 0: continue
            x = 120 + j * 300; yb = y + 120
            dr.rounded_rectangle((x, yb, x + 280, yb + 190), 18, fill=(21, 17, 19, int(255 * aa)) if j < 2 else (0, 0, 0, int(255 * aa)), outline=(RED if j == 0 else (60, 50, 55)) + (int(255 * aa),), width=2)
            dr.text((x + 22, yb + 26), a_, font=F('k', 38), fill=(RED if j == 0 else PAPER) + (int(255 * aa),))
            for q, row in enumerate(wrap(b_, F('m', 24), 240)): dr.text((x + 22, yb + 90 + q * 30), row, font=F('m', 24), fill=GREY + (int(255 * aa),))
        if xp and aout > 0:
            txt = f'{xp} XP'; ff = F('k', 40); dr.text((120, y + 40), txt, font=ff, fill=OK + (int(255 * aout),))
    elif k == 'ranks':
        y, aout = left_text(im, i, lt, d, 110)
        base = 850; bw = 300
        prog = eio((lt - 1.0) / (d - 2.2))
        for j, (n, l) in enumerate(RANKS):
            aa = back((lt - .5 - j * .35) / .6); h_ = int((250 + j * 85) * min(1, max(0, aa)))
            x = 120 + j * (bw + 40)
            if h_ <= 0: continue
            lit = prog * 5 > j
            dr.rounded_rectangle((x, base - h_, x + bw, base), 16, fill=(RED if j == 4 else (40, 30, 35)) + (int(255 * aout),) if lit else (24, 20, 23, int(255 * aout)),
                                 outline=(RED if lit else (60, 50, 55)) + (int(255 * aout),), width=3)
            dr.text((x + 22, base - h_ + 20), n.upper(), font=F('k', 44), fill=PAPER + (int(255 * aout),))
            for q, row in enumerate(wrap(l, F('m', 22), bw - 40)): dr.text((x + 22, base - h_ + 80 + q * 28), row, font=F('m', 22), fill=(GREY if not lit else PAPER) + (int(255 * aout),))
            dr.text((x + 22, base - 50), f'Ранг {j + 1}', font=F('s', 22), fill=GREY + (int(255 * aout),))
        dr.text((120, base + 30), 'У МОП своя лестница: Стажёр → Дилер → Хантер → Клоузер → Легенда · ранг вниз не падает', font=F('m', 26), fill=GREY + (int(255 * aout),))
    elif k == 'layers':
        y, aout = left_text(im, i, lt, d, 110)
        for j, (n, l) in enumerate(LAYERS):
            aa = ease((lt - .5 - j * .6) / .5) * aout
            if aa <= 0: continue
            x = 120 + j * 430; yb = 440 + int(40 * (1 - aa))
            dr.rounded_rectangle((x, yb, x + 400, yb + 230), 18, fill=(21, 17, 19, int(255 * aa)) if j < 3 else (0, 0, 0, int(255 * aa)), outline=(60, 50, 55, int(255 * aa)), width=2)
            dr.text((x + 24, yb + 22), f'СЛОЙ {j + 1}', font=F('s', 20), fill=RED + (int(255 * aa),))
            dr.text((x + 24, yb + 52), n, font=F('k', 38), fill=PAPER + (int(255 * aa),))
            for q, row in enumerate(wrap(l, F('m', 24), 350)): dr.text((x + 24, yb + 112 + q * 32), row, font=F('m', 24), fill=GREY + (int(255 * aa),))
        for j, (ic, n) in enumerate(BADGES):
            aa = back((lt - 3.2 - j * .3) / .5)
            if aa <= 0: continue
            a2 = min(1, aa) * aout; x = 120 + j * 285; yb = 760
            r_ = int(44 * min(1.15, aa))
            dr.rounded_rectangle((x, yb, x + 265, yb + 110), 18, fill=(21, 17, 19, int(255 * a2)), outline=(60, 50, 55, int(255 * a2)), width=2)
            dr.rounded_rectangle((x + 18, yb + 55 - r_, x + 18 + 2 * r_, yb + 55 + r_), 14, fill=RED + (int(255 * a2),))
            ff = F('k', 30); tw = dr.textlength(ic, font=ff); dr.text((x + 18 + r_ - tw / 2, yb + 36), ic, font=ff, fill=(255, 255, 255, int(255 * a2)))
            dr.text((x + 120, yb + 40), n, font=F('b', 23), fill=PAPER + (int(255 * a2),))
    elif k == 'launch':
        aout = 1 - ease((lt - (d - .4)) / .4)
        rng = np.random.default_rng(3)
        for q in range(90):   # конфетти
            x0, sp_, ph_ = rng.uniform(0, W), rng.uniform(120, 260), rng.uniform(0, 6)
            yq = (rng.uniform(-H, 0) + sp_ * lt) % (H + 80) - 40; xq = x0 + 30 * math.sin(lt * 2 + ph_)
            col = [RED, PAPER, WARN, OK][q % 4]; s_ = 6 + q % 5
            dr.rectangle((xq, yq, xq + s_, yq + s_ * 1.8), fill=col + (int(200 * ease(lt / .6) * aout),))
        a = ease((lt - .2) / .6) * aout; z = back((lt - .2) / .7)
        big = T('15.12', F('k', 300), RED + (255,), 1200, 1.0); big = big.crop(big.getbbox())
        if z > 0:
            bz = big.resize((max(1, int(big.width * z)), max(1, int(big.height * z))), Image.BICUBIC)
            im.alpha_composite(A(bz, a), (int((W - bz.width) / 2), int(150 + (1 - z) * 60)))
        for j, (txt, f_, col) in enumerate([(SC[i]['t'], F('k', 64), PAPER), (SC[i]['s'] + ' · опыт копится с 01.11', F('m', 36), GREY)]):
            aa = ease((lt - 1.0 - j * .3) / .5) * aout; ti = T(txt, f_, col + (255,), 1700)
            tw = ImageDraw.Draw(Image.new('L', (1, 1))).textlength(txt, font=f_)
            im.alpha_composite(A(ti, aa), (int((W - tw) / 2), 560 + j * 100))

CLIPS = {}
for p_ in plan:
    sc = SC[p_['i']]
    if sc['kind'] == 'clip':
        try: CLIPS[p_['i']] = clip_frames(sc['clip'][0], sc['clip'][1], sc['clip'][2], p_['d'])
        except Exception:
            if not os.environ.get('PREVIEW'): raise
            CLIPS[p_['i']] = [bytes(PW * PH * 3)]
PREV = [float(x) for x in os.environ.get('PREVIEW', '').split(',') if x]

enc = None if os.environ.get('PREVIEW') else subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', OUTF + '.v.mp4'], stdin=subprocess.PIPE)
for k in ([int(x * FPS) for x in PREV] if PREV else range(N)):
    t = k / FPS; im = BG.copy()
    im.alpha_composite(GLOW, (int(W * .7 - gs / 2 + 260 * math.sin(t * .4)), int(H * .3 - gs / 2 + 120 * math.cos(t * .31))))
    im.alpha_composite(GLOW, (int(-gs / 2 + 200 + 120 * math.cos(t * .35)), int(H - 300 - gs / 2 + 90 * math.sin(t * .27))))
    if t < INTRO:
        a = ease((t - .2) / .8); z = .9 + .1 * ease((t - .2) / 1.2)
        lg = LOGO_L.resize((int(LOGO_L.width * z), int(LOGO_L.height * z)), Image.BICUBIC)
        im.alpha_composite(A(lg, a), ((W - lg.width) // 2, (H - lg.height) // 2 - 40))
        dr = ImageDraw.Draw(im); wl = int(700 * ease((t - .9) / .8)); dr.rectangle((W / 2 - wl / 2, H / 2 + 110, W / 2 + wl / 2, H / 2 + 118), fill=RED)
        st = T('ПРИЛОЖЕНИЕ КОМАНДЫ · 2026', F('s', 30), GREY + (255,), 900)
        tw = dr.textlength('ПРИЛОЖЕНИЕ КОМАНДЫ · 2026', font=F('s', 30)); im.alpha_composite(A(st, ease((t - 1.3) / .6)), (int((W - tw) / 2), H // 2 + 150))
        if t > INTRO - .35: im = Image.blend(im, BG, ease((t - (INTRO - .35)) / .35))
    elif t < TOTAL - OUTRO:
        i = max(j for j in range(len(plan)) if plan[j]['t'] <= t); p_ = plan[i]; lt = t - p_['t']
        draw_scene(im, i, lt, p_['d'], t)
        dr = ImageDraw.Draw(im)
        if lt < .14 and i: dr.rectangle((0, 0, int(W * ease(lt / .14)), 8), fill=RED)
        dr.rectangle((0, H - 6, int(W * (t - INTRO) / (TOTAL - OUTRO - INTRO)), H), fill=RED)
        im.alpha_composite(A(LOGO_S, .8), (W - LOGO_S.width - 70, 60))
        for s0, s1, simg in SUBS:
            if s0 <= t < s1:
                a = min(ease((t - s0) / .15), 1 - ease((t - (s1 - .1)) / .1))
                im.alpha_composite(A(simg, a), ((W - simg.width) // 2, H - simg.height - 46)); break
    else:
        lt = t - (TOTAL - OUTRO); a = [ease((lt - q) / .5) for q in (0, .35, .7)]
        im.alpha_composite(A(LOGO_L, a[0]), ((W - LOGO_L.width) // 2, int(300 + 30 * (1 - a[0]))))
        dr = ImageDraw.Draw(im)
        for j, (txt, f_, col) in enumerate([('С 9 ноября — вся команда в приложении', F('k', 56), PAPER), ('Бот ARTGAME в Telegram → кнопка меню', F('m', 34), GREY)]):
            tw = dr.textlength(txt, font=f_); im.alpha_composite(A(T(txt, f_, col + (255,), 1700), a[j + 1]), (int((W - tw) / 2), 620 + j * 90))
        if lt > OUTRO - .8: im = Image.blend(im, Image.new('RGBA', (W, H), INK + (255,)), ease((lt - (OUTRO - .8)) / .8))
    if PREV: im.convert('RGB').save(f'{OUTF}.{t:.1f}.png'); continue
    enc.stdin.write(im.convert('RGB').tobytes())
    if k % 900 == 0: print('promo', k, '/', N, flush=True)
if enc: enc.stdin.close(); enc.wait()
if PREV: sys.exit(0)

SR = 44100; mw = OUTF + '.m.wav'
music.render(TOTAL, [p_['t'] for p_ in plan[1:]] + [TOTAL - OUTRO], INTRO, OUTRO, mw)
with wave.open(mw) as w: mus = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2).astype(np.float32) / 32767
voice = np.zeros(len(mus), np.float32)
for p_ in plan:
    vw = OUTF + f'.{p_["i"]}.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f'{VO}/promo/{p_["i"]:02d}.wav', '-ar', str(SR), '-ac', '1', vw], check=True)
    with wave.open(vw) as w: v = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32767
    os.remove(vw); a = int((p_['t'] + LEAD) * SR); b = min(len(voice), a + len(v)); voice[a:b] += v[:b - a]
env = np.clip(np.convolve((np.abs(voice) > 0.02).astype(np.float32), np.ones(int(.35 * SR)) / int(.35 * SR), 'same') * 3, 0, 1)
mix = mus * (0.55 - 0.40 * env)[:, None] + (voice / max(1e-6, np.abs(voice).max()) * 0.92)[:, None]
mix /= max(1.0, np.abs(mix).max() / 0.97)
aw = OUTF + '.a.wav'
with wave.open(aw, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype(np.int16).tobytes())
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', OUTF + '.v.mp4', '-i', aw, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', OUTF], check=True)
for f_ in (OUTF + '.v.mp4', aw, mw): os.remove(f_)
print('готово promo', round(TOTAL, 1), 'с')

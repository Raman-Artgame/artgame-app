"""Монтаж обучающего ролика роли: 1080×1920, 30 fps, для телефона.
Тёмный фон бренда, телефон с записью экрана, главы, субтитры, озвучка, своя музыка (music.py), свуши на склейках.
python edit_roles.py <роль> <папка записи> <папка озвучки> <папка картинок> <выход.mp4>"""
import glob, json, math, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

D = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, D)
import music  # noqa: E402

ROLE, REC, VO, IMG, OUTF = sys.argv[1:6]
R = json.load(open(os.path.join(D, 'scripts.json')))[ROLE]
SC = R['scenes']
DUR = json.load(open(f'{VO}/durations.json'))[ROLE]
MARKS = json.load(open(f'{REC}/marks.json'))
SRC = f'{REC}/screen.mp4'
if not os.path.exists(SRC):   # кадры CDP-скринкаста (переменная частота) → ровные 30 fps от t0
    fr = json.load(open(f'{REC}/frames.json')); t0 = json.load(open(f'{REC}/t0.json'))
    with open(f'{REC}/concat.txt', 'w') as c:
        c.write(f"file '{REC}/{fr[0][0]}'\nduration {max(0.001, fr[0][1] - t0):.4f}\n")
        for (a, ta), (_, tb) in zip(fr, fr[1:] + [[None, fr[-1][1] + 1]]):
            c.write(f"file '{REC}/{a}'\nduration {max(0.001, tb - ta):.4f}\n")
        c.write(f"file '{REC}/{fr[-1][0]}'\n")
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', f'{REC}/concat.txt', '-vf', 'fps=30,scale=780:1560,format=yuv420p',
                    '-c:v', 'libx264', '-crf', '14', '-preset', 'fast', SRC], check=True)
FD = '/usr/share/fonts/opentype/inter/'
F = lambda w, s: ImageFont.truetype(FD + {'b': 'InterDisplay-ExtraBold.otf', 'k': 'InterDisplay-Black.otf', 's': 'Inter-SemiBold.otf', 'm': 'Inter-Medium.otf'}[w], s)
W, H, FPS = 1080, 1920, 30
INK, PAPER, RED, GREY = (11, 9, 10), (245, 239, 241), (230, 0, 65), (168, 152, 158)
PW, PH, BZ, RAD = 600, 1200, 14, 60
PX, PY = (W - PW) // 2, 440
CHAR = {'support': 'ch_artist', 'artist': 'ch_artist', 'lead_artist': 'ch_cur', 'artist_pro': 'ch_cur', 'print_operator': 'ch_prod',
        'print_master': 'ch_prod', 'mop': 'ch_sales', 'lead_designer': 'ch_design', 'designer_asst': 'ch_design', 'head': 'ch_mgmt'}[ROLE]
INTRO, OUTRO, LEAD = 3.4, 3.6, 0.3

# ---------- план: сцена = отрезок записи, длина = озвучка + запас; длинный отрезок ускоряем (не больше 1.9×) ----------
plan, t = [], INTRO
for i, sc in enumerate(SC):
    s, e = MARKS[i]
    need = DUR[i] + LEAD + 0.55
    sp = max(1.0, min(1.9, (e - s) / need))
    d = max(need, (e - s) / sp)
    plan.append(dict(i=i, s=s, e=e, sp=sp, t=t, d=d)); t += d
TOTAL = t + OUTRO
N = int(round(TOTAL * FPS))

def ease(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def eio(x): x = max(0.0, min(1.0, x)); return x * x * (3 - 2 * x)

def wrap(txt, f, width):
    d = ImageDraw.Draw(Image.new('L', (1, 1))); rows, cur = [], ''
    for w_ in txt.split():
        n = (cur + ' ' + w_).strip()
        if d.textlength(n, font=f) > width and cur: rows.append(cur); cur = w_
        else: cur = n
    return rows + [cur]

def text_img(txt, f, col, width=W - 160, lh=1.12):
    rows = wrap(txt, f, width)
    im = Image.new('RGBA', (width, int(len(rows) * f.size * lh) + 12), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
    for k, r in enumerate(rows): dr.text((0, k * f.size * lh), r, font=f, fill=col)
    return im

def alpha(im, a):
    if a >= .999: return im
    if a <= 0: return Image.new('RGBA', im.size, (0, 0, 0, 0))
    r, g, b, al = im.split(); return Image.merge('RGBA', (r, g, b, al.point(lambda v: int(v * a))))

# ---------- статичные слои ----------
yy, xx = np.mgrid[0:H, 0:W]
bg = np.zeros((H, W, 3), np.float32) + np.array(INK, np.float32)
bg += (((xx % 72) == 0) | ((yy % 72) == 0))[..., None] * 7.0
bg *= (1 - 0.35 * ((yy / H - 0.5) ** 2 * 2 + (xx / W - .5) ** 2))[..., None]
BG = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert('RGBA')
gs = 1000; gy, gx = np.mgrid[0:gs, 0:gs]
g = np.exp(-(((gx - gs / 2) ** 2 + (gy - gs / 2) ** 2) / (2 * (gs / 5.5) ** 2)))
GLOW = Image.fromarray(np.dstack([np.full((gs, gs), c) for c in RED] + [g * 105]).astype(np.uint8), 'RGBA')
mask = Image.new('L', (PW, PH), 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, PW - 1, PH - 1), RAD - BZ, fill=255)
FRAME = Image.new('RGBA', (PW + 2 * BZ, PH + 2 * BZ), (0, 0, 0, 0))
ImageDraw.Draw(FRAME).rounded_rectangle((0, 0, PW + 2 * BZ - 1, PH + 2 * BZ - 1), RAD, fill=(24, 20, 23, 255), outline=(70, 60, 66, 255), width=3)
sh = Image.new('RGBA', (PW + 240, PH + 240), (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle((90, 110, PW + 150, PH + 170), RAD, fill=(0, 0, 0, 210)); SHADOW = sh.filter(ImageFilter.GaussianBlur(40))
RIM = Image.new('RGBA', (PW + 200, PH + 200), (0, 0, 0, 0))
ImageDraw.Draw(RIM).rounded_rectangle((60, 60, PW + 140, PH + 140), RAD + 8, outline=RED + (110,), width=5); RIM = RIM.filter(ImageFilter.GaussianBlur(14))
LOGO = Image.open(f'{IMG}/logo_dark.png').convert('RGBA'); LOGO = LOGO.resize((520, int(LOGO.height * 520 / LOGO.width)), Image.LANCZOS)
LOGO_S = LOGO.resize((260, int(LOGO.height * 260 / LOGO.width)), Image.LANCZOS)
CH = Image.open(f'{IMG}/{CHAR}.png').convert('RGBA'); CH = CH.resize((560, int(CH.height * 560 / CH.width)), Image.LANCZOS)

f_num, f_t, f_s, f_sub = F('s', 30), F('k', 76), F('m', 36), F('b', 46)
HEAD_L = []
for k, sc in enumerate(SC):
    HEAD_L.append((text_img(f'{k + 1:02d} / {len(SC):02d}', f_num, RED + (255,)), text_img(sc['t'], f_t, PAPER + (255,)), text_img(sc['s'], f_s, GREY + (255,))))

# субтитры: фразы по 1–2 строки, время — пропорционально буквам
def chunks(txt):
    out = []
    for sent in re.split(r'(?<=[.!?])\s+', txt.strip()):
        rows = wrap(sent, f_sub, W - 200)
        if len(rows) <= 2: out.append(sent); continue
        parts = re.split(r'(?<=[,:—])\s+', sent); cur = ''
        for pt in parts:
            n = (cur + ' ' + pt).strip()
            if len(wrap(n, f_sub, W - 200)) > 2 and cur: out.append(cur); cur = pt
            else: cur = n
        if cur:
            if len(wrap(cur, f_sub, W - 200)) > 2:   # всё ещё длинно — по словам
                ws = cur.split(); h = len(ws) // 2; out += [' '.join(ws[:h]), ' '.join(ws[h:])]
            else: out.append(cur)
    return out

SUBS = []   # (t0, t1, img)
for p_ in plan:
    cs = chunks(SC[p_['i']]['say']); tot = sum(len(c) for c in cs); t0 = p_['t'] + LEAD
    for c in cs:
        d = DUR[p_['i']] * len(c) / tot
        rows = wrap(c, f_sub, W - 200); lh = int(f_sub.size * 1.22)
        im = Image.new('RGBA', (W - 120, len(rows) * lh + 44), (0, 0, 0, 0)); dr = ImageDraw.Draw(im)
        dr.rounded_rectangle((0, 0, im.width - 1, im.height - 1), 26, fill=(0, 0, 0, 175))
        for k, r in enumerate(rows):
            tw = dr.textlength(r, font=f_sub); dr.text(((im.width - tw) / 2, 20 + k * lh), r, font=f_sub, fill=PAPER + (255,))
        SUBS.append((t0, t0 + d, im)); t0 += d

INTRO_L = [text_img('ОБУЧЕНИЕ · ПРИЛОЖЕНИЕ', F('s', 34), RED + (255,)), text_img(R['title'], F('k', 128 if len(R['title']) < 14 else 104), PAPER + (255,), W - 140, 1.0),
           text_img('Полторы минуты — и ты в деле', F('m', 44), GREY + (255,))]
OUT_L = [text_img('Всё по работе — в приложении', F('k', 66), PAPER + (255,), W - 180, 1.05), text_img('Бот ARTGAME в Telegram → кнопка меню', F('m', 38), GREY + (255,), W - 180)]

# ---------- кадры записи ----------
def frames(p_):
    n = int(round(p_['d'] * FPS)); span = p_['e'] - p_['s']
    vf = f'setpts=PTS/{p_["sp"]},fps={FPS},scale={PW}:{PH}:flags=lanczos,unsharp=5:5:0.5'
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', f'{p_["s"]:.3f}', '-t', f'{span:.3f}', '-i', SRC, '-vf', vf, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         capture_output=True, check=True).stdout
    sz = PW * PH * 3; fr = [raw[k * sz:(k + 1) * sz] for k in range(len(raw) // sz)]
    if not fr: fr = [bytes(sz)]
    while len(fr) < n: fr.append(fr[-1])
    return fr[:n]

def phone(buf, scale):
    scr = Image.frombytes('RGB', (PW, PH), buf).convert('RGBA'); scr.putalpha(mask)
    lay = FRAME.copy(); lay.alpha_composite(scr, (BZ, BZ))
    if abs(scale - 1) > 1e-3: lay = lay.resize((int(lay.width * scale), int(lay.height * scale)), Image.BICUBIC)
    return lay

enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '19', '-pix_fmt', 'yuv420p', OUTF + '.v.mp4'], stdin=subprocess.PIPE)
cur, CL, prev_last = -1, None, None
for k in range(N):
    t = k / FPS
    im = BG.copy()
    im.alpha_composite(GLOW, (int(W / 2 - gs / 2 + 300 * math.sin(t * .45)), int(300 - gs / 2 + 140 * math.cos(t * .33))))
    im.alpha_composite(GLOW, (int(-gs / 2 + 140 + 90 * math.cos(t * .4)), int(H - 520 + 100 * math.sin(t * .29))))
    dr = ImageDraw.Draw(im)
    if t < INTRO:
        a = [ease((t - d0) / .5) for d0 in (0.0, .25, .45, .7)]
        im.alpha_composite(alpha(LOGO, a[0]), (80, int(200 + 40 * (1 - a[0]))))
        im.alpha_composite(alpha(INTRO_L[0], a[1]), (80, int(560 + 50 * (1 - a[1]))))
        im.alpha_composite(alpha(INTRO_L[1], a[2]), (76, int(620 + 60 * (1 - a[2]))))
        y3 = 640 + INTRO_L[1].height
        im.alpha_composite(alpha(INTRO_L[2], a[3]), (80, int(y3 + 40 * (1 - a[3]))))
        wl = int((W - 160) * ease((t - .9) / .7)); dr.rectangle((80, y3 + 90, 80 + wl, y3 + 102), fill=RED + (255,))
        ca = ease((t - .5) / .8); im.alpha_composite(alpha(CH, ca), (W - CH.width + 40, int(H - CH.height - 60 + 120 * (1 - ca))))
        if t > INTRO - .35: im = Image.blend(im, BG, ease((t - (INTRO - .35)) / .35))
    elif t < TOTAL - OUTRO:
        i = max(j for j in range(len(plan)) if plan[j]['t'] <= t); p_ = plan[i]; lt = t - p_['t']
        if i != cur:
            if CL: prev_last = CL[-1]
            CL = frames(p_); cur = i
        buf = CL[min(int(lt * FPS), len(CL) - 1)]
        enter = ease((t - INTRO) / .7)
        scale = 1 + .02 * eio(lt / p_['d']) + (.035 * (1 - ease(lt / .3)) if i else 0)
        ph = phone(buf, scale)
        if lt < .25 and prev_last is not None and i:
            ph = Image.blend(phone(prev_last, scale), ph, eio(lt / .25))
        x = (W - ph.width) // 2; y = PY - BZ - (ph.height - PH - 2 * BZ) // 2 + int(1000 * (1 - enter))
        im.alpha_composite(SHADOW, (x - 120 + (ph.width - PW - 2 * BZ) // 2, y - 120))
        im.alpha_composite(RIM, (x - 60 - BZ + (ph.width - PW - 2 * BZ) // 2, y - 60 - BZ))
        im.alpha_composite(ph, (x, y))
        num, tit, sub = HEAD_L[i]; d = p_['d']
        ain = [ease((lt - d0) / .4) for d0 in (0, .07, .18)]
        aout = 1 - ease((lt - (d - .22)) / .22)
        im.alpha_composite(alpha(num, ain[0] * aout), (80, int(120 + 40 * (1 - ain[0]))))
        im.alpha_composite(alpha(tit, ain[1] * aout), (80, int(168 + 50 * (1 - ain[1]))))
        im.alpha_composite(alpha(sub, ain[2] * aout), (80, int(176 + tit.height + 40 * (1 - ain[2]))))
        seg = (W - 160 - (len(plan) - 1) * 8) / len(plan)
        for j in range(len(plan)):
            x0 = 80 + j * (seg + 8); dr.rounded_rectangle((x0, 72, x0 + seg, 80), 4, fill=(48, 40, 46, 255))
            fl = 1 if j < i else (lt / d if j == i else 0)
            if fl > 0: dr.rounded_rectangle((x0, 72, x0 + seg * fl, 80), 4, fill=RED + (255,))
        if lt < .14 and i: dr.rectangle((0, 0, int(W * ease(lt / .14)), 10), fill=RED + (255,))
        for s0, s1, simg in SUBS:
            if s0 <= t < s1:
                a = min(ease((t - s0) / .15), 1 - ease((t - (s1 - .1)) / .1))
                im.alpha_composite(alpha(simg, a), ((W - simg.width) // 2, H - simg.height - 70 + int(14 * (1 - a))))
                break
        im.alpha_composite(alpha(LOGO_S, .85 * aout if i == len(plan) - 1 else .85), (W - LOGO_S.width - 60, 118))
    else:
        lt = t - (TOTAL - OUTRO)
        a = [ease((lt - d0) / .5) for d0 in (0, .3, .6)]
        im.alpha_composite(alpha(LOGO, a[0]), ((W - LOGO.width) // 2, int(520 + 40 * (1 - a[0]))))
        im.alpha_composite(alpha(OUT_L[0], a[1]), (90, int(860 + 40 * (1 - a[1]))))
        im.alpha_composite(alpha(OUT_L[1], a[2]), (90, int(880 + OUT_L[0].height + 30 * (1 - a[2]))))
        im.alpha_composite(alpha(CH, a[2]), ((W - CH.width) // 2, H - CH.height + 40))
        if lt > OUTRO - .7: im = Image.blend(im, Image.new('RGBA', (W, H), INK + (255,)), ease((lt - (OUTRO - .7)) / .7))
    enc.stdin.write(im.convert('RGB').tobytes())
    if k % 600 == 0: print(ROLE, k, '/', N, flush=True)
enc.stdin.close(); enc.wait()

# ---------- звук: музыка (тише под голосом) + озвучка ----------
SR = 44100
mw = OUTF + '.m.wav'
music.render(TOTAL, [p_['t'] for p_ in plan[1:]] + [TOTAL - OUTRO], INTRO, OUTRO, mw)
with wave.open(mw) as w: mus = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2).astype(np.float32) / 32767
voice = np.zeros(len(mus), np.float32)
for p_ in plan:
    vw = OUTF + f'.{p_["i"]}.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', f'{VO}/{ROLE}/{p_["i"]:02d}.wav', '-ar', str(SR), '-ac', '1', vw], check=True)
    with wave.open(vw) as w: v = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32767
    os.remove(vw)
    a = int((p_['t'] + LEAD) * SR); b = min(len(voice), a + len(v)); voice[a:b] += v[:b - a]
env = np.convolve((np.abs(voice) > 0.02).astype(np.float32), np.ones(int(.35 * SR)) / int(.35 * SR), 'same')
env = np.clip(env * 3, 0, 1)
gain = 0.55 - 0.40 * env
mix = mus * gain[:, None] + (voice / max(1e-6, np.abs(voice).max()) * 0.92)[:, None]
mix /= max(1.0, np.abs(mix).max() / 0.97)
aw = OUTF + '.a.wav'
with wave.open(aw, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix * 32767).astype(np.int16).tobytes())
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', OUTF + '.v.mp4', '-i', aw, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', OUTF], check=True)
for f_ in (OUTF + '.v.mp4', aw, mw): os.remove(f_)
print('готово', ROLE, round(TOTAL, 1), 'с')

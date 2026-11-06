"""Своя музыка для ролика: 120 BPM, Am–F–C–G, бочка/клэп/хэты/бас/пэд/арпеджио + свуши на склейках. Без чужих сэмплов."""
import numpy as np, wave, sys, json

SR = 44100
BPM = 120
BEAT = 60 / BPM

def env(n, a, d, sus=0.0, curve=6.0):
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4)) * (sus + (1 - sus) * np.exp(-curve * np.maximum(0, t - a) / max(d, 1e-4)))
    return e

def lp(x, k):   # простой ФНЧ: скользящее среднее k раз
    for _ in range(2):
        x = np.convolve(x, np.ones(k) / k, mode='same')
    return x

def hp(x):
    return np.diff(x, prepend=0)

def note(m):
    return 440 * 2 ** ((m - 69) / 12)

def saw(f, n, harm=12, det=0.0):
    t = np.arange(n) / SR
    out = np.zeros(n)
    for h in range(1, harm + 1):
        out += np.sin(2 * np.pi * f * h * t * (1 + det)) / h
    return out * 0.6

def kick():
    n = int(0.45 * SR); t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 7.5) + 0.25 * np.sin(ph * 2) * np.exp(-t * 30)

def clap(rng):
    n = int(0.25 * SR); t = np.arange(n) / SR
    x = hp(rng.standard_normal(n)) * (np.exp(-t * 18) + 0.6 * np.exp(-((t - 0.012) ** 2) / 1e-5))
    return lp(x, 3) * 0.5

def hat(rng, open_=False):
    n = int((0.18 if open_ else 0.05) * SR); t = np.arange(n) / SR
    return hp(hp(rng.standard_normal(n))) * np.exp(-t * (14 if open_ else 70)) * 0.09

def place(buf, x, at, g=1.0):
    i = int(at * SR)
    if i >= len(buf): return
    j = min(len(buf), i + len(x)); buf[i:j] += g * x[:j - i]

def whoosh(rng, dur=0.7):
    n = int(dur * SR); t = np.arange(n) / SR
    x = rng.standard_normal(n)
    out = np.zeros(n); k0 = 60
    # нарастающий «свуш»: окно сглаживания уменьшается — шум светлеет
    seg = n // 14
    for s in range(14):
        k = max(2, int(k0 * (1 - s / 14)))
        a, b = s * seg, min(n, (s + 1) * seg + 400)
        out[a:b] += lp(x[a:b], k)
    e = (t / dur) ** 2.2 * np.exp(-np.maximum(0, t - dur * 0.92) * 40)
    return out * e * 1.8

def impact():
    n = int(1.2 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * (38 + 40 * np.exp(-t * 6)) * t) * np.exp(-t * 3.2) * 0.9

def render(total, cuts, intro, outro, path):
    rng = np.random.default_rng(7)
    N = int(total * SR) + SR
    drums, bass, pad, arp, fx = (np.zeros(N) for _ in range(5))
    duck = np.ones(N)
    prog = [57, 53, 48, 55]                       # A F C G (корни, октава баса ниже)
    chords = {57: [57, 60, 64], 53: [53, 57, 60], 48: [48, 52, 55, 59], 55: [55, 59, 62]}
    K, C = kick(), clap(rng)
    bar = 4 * BEAT
    nbars = int(total / bar) + 2
    for b in range(nbars):
        t0 = b * bar
        root = prog[b % 4]
        # пэд: весь ролик
        n = int(bar * SR)
        ch = sum(saw(note(m), n, 6, 0.003) + saw(note(m), n, 6, -0.003) for m in chords[root])
        place(pad, lp(ch, 9) * env(n, 0.25, bar, 0.7, 1.2) * 0.13, t0)
        drums_on = intro <= t0 < total - outro
        for q in range(4):
            tb = t0 + q * BEAT
            if drums_on:
                place(drums, K, tb, 0.95)
                i = int(tb * SR); m = min(N, i + int(0.22 * SR))
                duck[i:m] = np.minimum(duck[i:m], 0.35 + 0.65 * np.linspace(0, 1, m - i) ** 0.6)
                if q in (1, 3): place(drums, C, tb, 0.55)
                place(drums, hat(rng, q == 3), tb + BEAT / 2, 1.0)
                place(drums, hat(rng), tb + BEAT / 4, 0.45); place(drums, hat(rng), tb + 3 * BEAT / 4, 0.45)
            # бас восьмыми
            if t0 >= intro - bar:
                for e8 in range(2):
                    nb = int(BEAT / 2 * SR * 0.9)
                    f = note(root - 24 + (12 if (q * 2 + e8) % 4 == 3 else 0))
                    place(bass, lp(saw(f, nb, 8), 6) * env(nb, 0.005, 0.18, 0.4, 3) * 0.42, tb + e8 * BEAT / 2)
            # арпеджио шестнадцатыми — в середине для энергии
            if drums_on and t0 >= intro + 2 * bar:
                for s in range(4):
                    m = chords[root][(q * 4 + s) % len(chords[root])] + 12
                    ns = int(BEAT / 4 * SR)
                    place(arp, saw(note(m), ns, 5) * env(ns, 0.003, 0.09, 0.0, 5) * 0.07, tb + s * BEAT / 4)
    for c in cuts:
        place(fx, whoosh(rng), c - 0.65, 0.35)
    place(fx, impact(), intro, 0.8)
    place(fx, impact(), total - outro, 0.6)
    mix = drums * 0.9 + (bass + pad + arp) * duck + fx
    # выход: затухание в конце
    t = np.arange(N) / SR
    mix *= np.clip((total - t) / 1.8, 0, 1) * np.clip(t / 0.4, 0, 1)
    mix = np.tanh(mix * 1.6) * 0.8
    mix /= np.max(np.abs(mix)) / 0.89
    st = np.stack([mix, np.roll(mix, 90) * 0.97], 1)   # лёгкое стерео
    with wave.open(path, 'wb') as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st[:int(total * SR)] * 32767).astype(np.int16).tobytes())

if __name__ == '__main__':
    a = json.loads(sys.argv[1])
    render(a['total'], a['cuts'], a['intro'], a['outro'], a['out'])

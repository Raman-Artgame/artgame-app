"""Озвучка роликов: piper (русский голос, офлайн) → WAV на каждую сцену + durations.json.
python tts.py <голос.onnx> <папка вывода> [роль ...]"""
import json, os, re, subprocess, sys, wave

D = os.path.dirname(os.path.abspath(__file__))
VOICE, OUT = sys.argv[1], sys.argv[2]
ROLES = sys.argv[3:]
S = json.load(open(os.path.join(D, 'scripts.json')))
if os.path.exists(os.path.join(D, 'promo.json')):
    S['promo'] = json.load(open(os.path.join(D, 'promo.json')))
FIX = [(r'Хэд', 'Хэд'), (r'\bКП\b', 'капэ'), (r'\bМОП\b', 'моп'), (r'\bXS\b', 'икс эс'), (r'\bXL\b', 'икс эль'), (r'\bФОТ\b', 'фот'),
       (r'Битрикс', 'Битрикс'), (r'Телеграме', 'Телеграме'), (r'рилс', 'рилс'), (r'«|»', '')]


def say(text):
    for a, b in FIX:
        text = re.sub(a, b, text)
    return text


dur = {}
for role, r in S.items():
    if role.startswith('_') or (ROLES and role not in ROLES):
        continue
    os.makedirs(f'{OUT}/{role}', exist_ok=True)
    dur[role] = []
    for i, sc in enumerate(r['scenes']):
        f = f'{OUT}/{role}/{i:02d}.wav'
        subprocess.run([sys.executable, '-m', 'piper', '-m', VOICE, '-c', VOICE + '.json', '-f', f, '--length-scale', '0.92',
                        '--sentence-silence', '0.25'], input=say(sc['say']).encode(), check=True, capture_output=True)
        with wave.open(f) as w:
            dur[role].append(round(w.getnframes() / w.getframerate(), 2))
    print(role, sum(dur[role]), dur[role], flush=True)
old = json.load(open(f'{OUT}/durations.json')) if os.path.exists(f'{OUT}/durations.json') else {}
json.dump({**old, **dur}, open(f'{OUT}/durations.json', 'w'), indent=1)

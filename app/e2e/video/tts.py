"""Озвучка роликов → WAV на каждую сцену + durations.json.
python tts.py <голос.onnx | google:<голос> | eleven:<voice_id>> <папка вывода> [роль ...]
google: ключ в GOOGLE_TTS_KEY (Cloud Text-to-Speech, напр. google:ru-RU-Chirp3-HD-Charon); eleven: ключ в ELEVENLABS_API_KEY.
Иначе — piper офлайн."""
import base64, json, os, re, subprocess, sys, urllib.request, wave

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


def cloud(text, f):
    kind, voice = VOICE.split(':', 1)
    if kind == 'google':
        body = {'input': {'text': text}, 'voice': {'languageCode': 'ru-RU', 'name': voice},
                'audioConfig': {'audioEncoding': 'LINEAR16', 'sampleRateHertz': 44100}}
        rq = urllib.request.Request('https://texttospeech.googleapis.com/v1/text:synthesize?key=' + os.environ['GOOGLE_TTS_KEY'],
                                    json.dumps(body).encode(), {'Content-Type': 'application/json'})
        open(f, 'wb').write(base64.b64decode(json.load(urllib.request.urlopen(rq))['audioContent']))
    else:
        rq = urllib.request.Request(f'https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=pcm_44100',
                                    json.dumps({'text': text, 'model_id': 'eleven_multilingual_v2',
                                                'voice_settings': {'stability': 0.4, 'similarity_boost': 0.8, 'style': 0.35}}).encode(),
                                    {'Content-Type': 'application/json', 'xi-api-key': os.environ['ELEVENLABS_API_KEY']})
        pcm = urllib.request.urlopen(rq).read()
        with wave.open(f, 'wb') as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100); w.writeframes(pcm)


dur = {}
for role, r in S.items():
    if role.startswith('_') or (ROLES and role not in ROLES):
        continue
    os.makedirs(f'{OUT}/{role}', exist_ok=True)
    dur[role] = []
    for i, sc in enumerate(r['scenes']):
        f = f'{OUT}/{role}/{i:02d}.wav'
        if ':' in VOICE: cloud(sc['say'].replace('«', '').replace('»', ''), f)
        else: subprocess.run([sys.executable, '-m', 'piper', '-m', VOICE, '-c', VOICE + '.json', '-f', f, '--length-scale', '0.92',
                        '--sentence-silence', '0.25'], input=say(sc['say']).encode(), check=True, capture_output=True)
        with wave.open(f) as w:
            dur[role].append(round(w.getnframes() / w.getframerate(), 2))
    print(role, sum(dur[role]), dur[role], flush=True)
old = json.load(open(f'{OUT}/durations.json')) if os.path.exists(f'{OUT}/durations.json') else {}
json.dump({**old, **dur}, open(f'{OUT}/durations.json', 'w'), indent=1)

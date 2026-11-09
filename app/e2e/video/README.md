# Обучающие ролики (HEAD 08.11)

1. Стенд как для e2e (`app/README.md`): `fake_api.py` на чистой базе + `vite preview --port 4173`.
2. Озвучка (HEAD 09.11 — ElevenLabs, голос «Николай», модель v3): `python tts.py eleven:3EuKHIEZbSzrHGNmdYsx <vo>` (ключ ELEVENLABS_API_KEY; все 10 ролей ≈ 8,5 тыс. символов). Запасной офлайн-вариант: `python tts.py <ru-голос.onnx> <vo>` → `vo/<роль>/NN.wav`, `vo/durations.json`. Голос piper `voice-ru-irinia-medium` (релиз rhasspy/piper v0.0.2).
   Снимок «Значений» для CONSTS: `{ключ: значение}` строк со статусом «Утверждено».
3. Запись роли (каждую — на чистой базе): `CONSTS=<снимок «Значений».json> node rec_roles.cjs <роль> <rec/роль> vo/durations.json <картинки>`.
   Картинки: из `design-kit/assets` (wall1.jpg, s05.jpg, s02.jpg, logo_dark.png, ch_*.png, team.jpg) + receipt.png.
4. Монтаж: `python edit_roles.py <роль> <rec/роль> <vo> <картинки> <роль>.mp4`; презентация — `python edit_promo.py <rec> <vo> <картинки> promo.mp4` (после роликов ролей).

Тексты меняются в `scripts.json` и `promo.json`, потом шаги 2–4. Цифры на экранах — из «Значений», в сценарии их не вписываем.

// Сквозной тест «Мой путь» (HEAD 11.11): Ангелина (Художник, и.о. Главного) видит путь к Главному первой карточкой
// «Кабинета», Куаныш (Главный) — путь к Художнику-Про; числа — из «Значений». API — e2e/fake_api.py.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const shots = process.env.SHOTS || '/var/tmp'

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.goto('http://127.0.0.1:4173/')
  await p.locator('nav').waitFor()
  return p
}
async function tab(p, name) { await p.locator('nav').getByRole('button', { name, exact: true }).click() }
// длинная карточка целиком: нижнее меню на снимке не перекрывает текст (на телефоне оно внизу экрана)
const long = async (p, loc, f) => { await p.evaluate(() => document.querySelector('nav').style.visibility = 'hidden')
  await loc.screenshot({ path: `${shots}/${f}.png` }); await p.evaluate(() => document.querySelector('nav').style.visibility = '') }
const noWide = async p => assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'нет горизонтальной прокрутки')

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  await call(1000, '/_e2e/consts', { 'norm.mural.medium': '10', 'curator.report_time': 'по окончании смены', 'curator.report_photos': '3',
    'curator.final_report_days': '3', 'shift.hours': '10', 'pay.artist.shift': '15000', 'pay.chief.shift': '20000' })
  const ids = {}
  for (const [tg, name, role] of [[5101, 'Ангелина', 'artist'], [5102, 'Куаныш', 'lead_artist']]) {
    ids[tg] = (await call(tg, '/register', { full_name: name })).id
    await call(1000, `/people/${ids[tg]}`, { role_code: role, zones: ['mural'] })
  }
  await call(1000, `/people/${ids[5101]}`, { acting_role: 'lead_artist', acting_promo: '2026-12-15', acting_note: 'День рождения команды!' })

  // Ангелина: «Мой путь» к Главному — первая карточка «Кабинета», дни до повышения
  const a = await open(b, 5101)
  await tab(a, 'Кабинет')
  const mp = a.locator('.mypath')
  await mp.getByText('Как стать Главным художником').waitFor()
  await mp.getByText(/До повышения \d+ дн\./).waitFor()
  await a.screenshot({ path: `${shots}/1-angelina-kabinet.png` })
  await mp.getByRole('button', { name: 'Открыть' }).click()
  await mp.getByText(/выше нормы — 10 м² Среднего за смену/).waitFor()   // число из «Значений»
  await mp.locator('.growrow').first().click()
  await mp.getByText('готово 1 из 8').waitFor()
  await noWide(a)
  await long(a, mp, '2-angelina-cheklist')
  const seg = async (p, t, f) => { await p.locator('.pathseg').getByRole('button', { name: t }).click(); await noWide(p)
    await long(p, p.locator('.mypath'), f) }
  await a.locator('.pathseg').getByRole('button', { name: 'Что знать' }).click()
  await mp.getByText('Что меняется').waitFor()
  await seg(a, 'Что знать', '2b-angelina-znat')
  await seg(a, 'Шаги', '2c-angelina-shagi')
  await a.locator('.pathseg').getByRole('button', { name: 'В приложении' }).click()
  await mp.getByText(/по окончании смены — статус и 3 фото/).waitFor()
  await seg(a, 'В приложении', '2d-angelina-prilozhenie')
  await seg(a, 'Чек-лист', '2e-angelina-cheklist-snova')
  await mp.getByText('готово 1 из 8').waitFor()   // отметка не пропала
  // путь к Главному не повторяется в «Правилах игры» художника; путь к Про — в «Правилах игры» Главного
  const folds = a.locator('.dutyfold')
  assert.strictEqual(await folds.count(), 2)
  await folds.nth(1).getByRole('button', { name: 'Открыть' }).click()
  assert.strictEqual(await folds.nth(1).getByText('Как стать Главным художником').count(), 0)

  // Куаныш: путь к Художнику-Про
  const k = await open(b, 5102)
  await tab(k, 'Кабинет')
  const kp = k.locator('.mypath')
  await kp.getByText('Как стать Художником-Про').waitFor()
  await k.screenshot({ path: `${shots}/3-kuanysh-kabinet.png` })
  await kp.getByRole('button', { name: 'Открыть' }).click()
  await kp.getByText('Как подтверждаем: экзамен оператора у Мастера печати').waitFor()
  await noWide(k)
  await long(k, kp, '4-kuanysh-cheklist')
  await k.locator('.pathseg').getByRole('button', { name: 'Что знать' }).click()
  await kp.getByText('Проверяю планы Главных').waitFor()
  await long(k, kp, '4b-kuanysh-znat')
  await k.locator('.pathseg').getByRole('button', { name: 'Шаги' }).click()
  await long(k, kp, '4c-kuanysh-shagi')
  await k.locator('.dutyfold').first().getByRole('button', { name: 'Открыть' }).click()
  assert.strictEqual(await k.locator('.dutyfold').getByText('Как стать Художником-Про').count(), 0)
  console.log('put ok')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

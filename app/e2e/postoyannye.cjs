// Сквозной тест «Постоянные оплаты» (HEAD 12.11): в день оплаты — «Оплатить сегодня» на Пульте, переход в «Финансы → Деньги»,
// «Оплачено» переводом без чека не нажимается, с чеком — оплачено; подписка — автосписание записано само. API — e2e/fake_api.py.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const DB = process.env.ARTGAME_DATABASE_URL
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const sql = q => execSync(`psql "${DB}" -qAtc "${q}"`).toString().trim()
const shots = process.env.SHOTS || '/var/tmp'

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'Раман HEAD' })
  await call(1000, '/_e2e/consts', { 'fin.fixed.rent_studio_ast': 300000, 'fin.fixed.rent_office_sales': 100000, 'fin.fixed.rent_shop': 150000,
    'fin.fixed.rent_workshop_ast': 200000, 'fin.fixed.rent_workshop_shym': 120000, 'fin.fixed.internet_ast': 17000, 'fin.fixed.telephony': 15000,
    'fin.fixed.hosting': 10000, 'fin.fixed.sub.gigapixel': 10000, 'fin.fixed.sub.freepik': 10000, 'fin.fixed.sub.chatgpt': 10000,
    'fin.fixed.sub.claude': 50000, 'fin.fixed.bitrix_year': 350000, 'fin.fixed.tenders_year': 100000, 'fin.fixed.wazzup': 24000 })
  const day = +sql("SELECT extract(day FROM (now() AT TIME ZONE 'Asia/Almaty'))::int")
  sql(`UPDATE fin_recurring SET start_date = (now() AT TIME ZONE 'Asia/Almaty')::date - 3`)
  sql(`UPDATE fin_recurring SET day = ${day} WHERE title IN ('Аренда студии, Астана', 'Баланс телефонии', 'Claude')`)
  sql(`UPDATE fin_recurring SET day = ${day > 1 ? day - 1 : 1} WHERE title = 'Интернет, Астана'`)   // вчера — просрочено (если не 1-е)

  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  const d = sign(1000)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.goto('http://127.0.0.1:4173/')
  const ask = p.locator('.qrow', { hasText: 'Оплатить сегодня' })
  await ask.waitFor()
  assert((await ask.innerText()).includes('Аренда студии'), 'на Пульте — аренда студии')
  assert(!(await ask.innerText()).includes('Claude'), 'автосписание — не к оплате')
  await ask.screenshot({ path: `${shots}/pult-oplatit.png` })
  await p.screenshot({ path: `${shots}/pult.png` })
  await ask.click()
  const card = p.locator('.card', { hasText: 'Постоянные оплаты' }).first()
  await card.waitFor()
  await card.locator('.row', { hasText: 'Аренда студии' }).waitFor()
  await card.screenshot({ path: `${shots}/postoyannye.png` })
  const rent = card.locator('.row.bill', { hasText: 'Аренда студии' })
  await rent.getByRole('button', { name: 'Оплачено' }).click()
  const ok = rent.getByRole('button', { name: /^Оплачено 300/ })
  assert(await ok.isDisabled(), 'переводом без чека — нельзя')
  await rent.locator('.receipt input').first().setInputFiles(__dirname + '/chek.png')
  await p.waitForTimeout(400)
  await rent.screenshot({ path: `${shots}/oplatit-chek.png` })
  assert(!(await ok.isDisabled()), 'с чеком — можно')
  await ok.click()
  await card.locator('.row.bill', { hasText: 'Аренда студии' }).locator('.ok').waitFor()
  const led = p.locator('.card', { hasText: 'Движение денег' })
  await led.locator('.row', { hasText: 'Автосписание: Claude' }).waitFor()
  await led.locator('.row', { hasText: 'Постоянная оплата: Аренда студии' }).waitFor()
  await card.screenshot({ path: `${shots}/postoyannye-oplacheno.png` })
  await p.screenshot({ path: `${shots}/dengi-full.png`, fullPage: true })
  // переносы: ни одна строка не шире экрана
  const wide = await p.evaluate(() => [...document.querySelectorAll('.row.bill')].filter(e => e.scrollWidth > e.clientWidth + 1).length)
  assert.strictEqual(wide, 0, 'строки не вылезают за экран')
  console.log('postoyannye ok')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

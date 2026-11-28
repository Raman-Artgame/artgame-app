// Сквозной тест «Бюджет: план и факт» (HEAD 26.11: «как мне сюда внести или подтвердить, что я уже что-то оплатил?»):
// HEAD жмёт строку бюджета → окно «Оплачено» (сумма из плана, дата, способ, чек) → платёж графика закрыт, факт обновился.
// Неоплаченное в этом месяце выделено с датой платежа; внесённое через «+ Общий» второй раз не предлагается.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const sql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -Atc "${q}"`).toString().trim()
const shots = process.env.SHOTS || '/var/tmp'
const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Almaty' })

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'Раман HEAD' })
  await call(1000, '/_e2e/consts', { 'fin.fixed.rent_studio_ast': 300000, 'fin.fixed.rent_office_sales': 100000, 'fin.fixed.rent_shop': 150000,
    'fin.fixed.rent_workshop_ast': 200000, 'fin.fixed.rent_workshop_shym': 120000, 'fin.fixed.internet_ast': 17000, 'fin.fixed.telephony': 15000,
    'fin.fixed.hosting': 10000, 'fin.fixed.sub.claude': 50000, 'fin.fixed.sub.gigapixel': 10000, 'fin.fixed.sub.freepik': 10000,
    'fin.fixed.sub.chatgpt': 10000, 'fin.fixed.sub.gworkspace': 13600 })
  // график запущен «вчера»: подписки с датой раньше (Gigapixel 1-го) всё равно записываются сами — месяц запуска целиком (HEAD 26.11)
  sql(`UPDATE fin_recurring SET start_date = CASE WHEN auto THEN (now() AT TIME ZONE 'Asia/Almaty')::date - 1 ELSE date_trunc('month', now() AT TIME ZONE 'Asia/Almaty')::date END`)
  sql(`UPDATE fin_recurring SET day = 1 WHERE title = 'Gigapixel'`)
  sql(`UPDATE fin_recurring SET day = 1 WHERE title = 'Аренда студии, Астана'`)
  // мастерскую HEAD уже внёс через «+ Общий» — без привязки к графику
  const art = sql(`SELECT code FROM fin_articles WHERE plan_key='fin.fixed.rent_workshop_ast'`)
  await call(1000, '/fin/ledger', { client_uid: crypto.randomUUID(), op_date: today(), account: 'kaspi', amount: 208000, article: art })

  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  const d = sign(1000)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.route('https://fonts.googleapis.com/**', r => r.fulfill({ body: '', contentType: 'text/css' }))
  await p.goto('http://127.0.0.1:4173/')
  const nav = p.locator('nav')
  await nav.locator('button').first().waitFor()
  await nav.getByRole('button', { name: /^Финансы/ }).click()
  await p.locator('.segf').getByRole('button', { name: 'Месяц' }).click()
  const card = p.locator('.card', { hasText: 'Бюджет: план и факт' })
  await card.waitFor()
  const studio = card.locator('.brow', { hasText: 'Аренда студии' })
  await studio.getByText(/не оплачено/).waitFor()
  assert.ok(await studio.evaluate(x => x.classList.contains('unpaid')), 'неоплаченное выделено')
  const shop = card.locator('.brow', { hasText: 'Аренда мастерской Астана' })
  await shop.locator('.ok', { hasText: 'оплачено' }).waitFor()        // внесено через «+ Общий» — уже оплачено
  const giga = card.locator('.brow', { hasText: 'Gigapixel' })
  await giga.locator('.ok', { hasText: 'списано' }).waitFor()          // автосписание записалось само, без чека
  await giga.getByText(/10\s000\s₸\s*\/\s*10\s000/).waitFor()
  await card.locator('.brow', { hasText: 'Google Workspace' }).getByText(/спишется само|списано/).waitFor()   // автосписание впереди — не «не оплачено»
  await card.scrollIntoViewIfNeeded()
  await card.screenshot({ path: `${shots}/byudzhet-1-stroki.png` })

  await studio.click()
  const sh = p.locator('.sheetbox')
  await sh.getByPlaceholder('Сумма, ₸').waitFor()
  assert.strictEqual(await sh.getByPlaceholder('Сумма, ₸').inputValue(), '300000', 'сумма подставлена из плана')
  const ok = sh.getByRole('button', { name: /^Оплачено 300/ })
  assert.ok(await ok.isDisabled(), 'переводом без чека — нельзя')
  await sh.locator('.receipt input').first().setInputFiles(__dirname + '/chek.png')
  await sh.locator('.receipt.has').waitFor()
  await p.waitForTimeout(500)
  await p.screenshot({ path: `${shots}/byudzhet-2-oplacheno.png` })
  await ok.click()
  await sh.waitFor({ state: 'detached' })
  await studio.locator('.ok', { hasText: 'оплачено' }).waitFor()
  await studio.getByText(/300\s000\s₸\s*\/\s*300\s000/).waitFor()     // факт обновился сразу
  assert.strictEqual(sql(`SELECT count(*) FROM fin_ledger WHERE status='active' AND source_ref LIKE 'recurring:%' AND note LIKE 'Постоянная оплата: Аренда студии%'`), '1')
  await card.screenshot({ path: `${shots}/byudzhet-3-posle.png` })

  // уже оплаченное: окно говорит «уже внесено», формы нет
  await shop.click()
  await sh.getByText(/уже внесено 208\s000/).waitFor()
  assert.strictEqual(await sh.getByPlaceholder('Сумма, ₸').count(), 0)
  await p.waitForTimeout(500)
  await p.screenshot({ path: `${shots}/byudzhet-4-uzhe.png` })
  await sh.getByRole('button', { name: 'Понятно' }).click()
  // «Деньги»: в графике мастерская тоже оплачена — напоминать не будет
  await p.locator('.segf').getByRole('button', { name: 'Деньги' }).click()
  await p.locator('.row.bill', { hasText: 'Аренда мастерской, Астана' }).locator('.ok').waitFor()
  assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'страница шире экрана')
  await b.close()
  console.log('OK byudzhet_oplacheno')
})().catch(e => { console.error(e); process.exit(1) })

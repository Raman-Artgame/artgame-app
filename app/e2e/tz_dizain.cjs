// Сквозной тест «ТЗ дизайнеру» (HEAD 26.11 «все окей, давай начинаем работу»): МОП на одном экране ставит задачу со сроком,
// материалами и лёгким брифом → клиент по ссылке без входа отвечает на бриф (RU/ҚАЗ) и прикладывает фото → у дизайнера «Сегодня»,
// доска со сроками и карточка с ТЗ → «Вопрос МОП» → строка у МОП в «Сегодня» → ответ возвращает задачу в работу.
// API — e2e/fake_api.py (Битрикс подменён); экран — vite preview :4173.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const raw = async (path, body) => (await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json()
const bxCalls = async () => (await fetch(API + '/_e2e/bx_calls')).json()
const shots = process.env.SHOTS || '/var/tmp'

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.route('https://fonts.googleapis.com/**', r => r.fulfill({ body: '', contentType: 'text/css' }))
  await p.route('https://upload.example/**', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'drvBIG00000301' }) }))
  await p.goto('http://127.0.0.1:4173/')
  return p
}
async function tab(p, name) {
  const nav = p.locator('nav')
  const re = new RegExp(`^${name}\\s*\\d*$`)
  await nav.locator('button').first().waitFor()
  if (await nav.getByRole('button', { name: re }).waitFor({ timeout: 1500 }).then(() => true, () => false)) return nav.getByRole('button', { name: re }).click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}
const fits = async (p, what) => assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${what}: ничего не уезжает вбок`)

const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const ids = {}
  for (const [tg, name, role, zones, bxu] of [[6000, 'Ануар', 'mop', ['sales'], 4565], [7100, 'Малика', 'designer_asst', ['design'], 4693]]) {
    ids[tg] = (await call(tg, '/register', { full_name: name })).id
    await call(1000, `/people/${ids[tg]}`, { role_code: role, zones, bitrix_user_id: bxu })
  }
  const soon = new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 10)

  // 1. МОП: «Нужен дизайн» — один экран. Без срока кнопка не нажимается.
  const m = await open(b, 6000)
  let up = 400
  await m.unroute('https://upload.example/**')
  await m.route('https://upload.example/**', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'drvBIG00000' + (++up) }) }))
  await tab(m, 'Сделки')
  await m.locator('.card input[placeholder^="Номер"]').fill('1601')
  await m.locator('.kc', { hasText: '№ 1601' }).first().click()
  await m.locator('.dtdeal').getByRole('button', { name: '+ Нужен дизайн' }).click()
  const sh = m.locator('.sheetbox')
  await sh.locator('input').first().fill('Школа: коридоры и столовая')
  assert.ok(await sh.getByRole('button', { name: 'Отправить дизайнеру' }).isDisabled(), 'без срока эскиза не отправить')
  await sh.locator('input[type=date]').first().fill(soon)
  await sh.locator('.dtmat input[type=file]').last().setInputFiles([
    { name: 'Стена 1.png', mimeType: 'image/png', buffer: PNG }, { name: 'Стена 2.png', mimeType: 'image/png', buffer: PNG },
    { name: 'Развёртка 2 этаж.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4') }])
  await sh.locator('.dtstrip .dtthumb').nth(2).waitFor()
  for (const x of ['Дети', 'Графика', 'Энергия']) await sh.locator('.dtq button', { hasText: x }).click()
  await sh.locator('textarea').fill('Каждый этаж своя тема. Без чёрного. Логотип школы.')
  await m.waitForTimeout(400)
  await fits(m, 'окно «Нужен дизайн»')
  await m.screenshot({ path: `${shots}/tz-1-mop-nuzhen-dizain.png` })
  await sh.locator('.mbody').evaluate(e => e.scrollTo(0, e.scrollHeight)); await m.waitForTimeout(300)
  await m.screenshot({ path: `${shots}/tz-1b-mop-nuzhen-dizain-niz.png` })
  const before = (await bxCalls()).length
  await sh.getByRole('button', { name: /клиенту бриф ссылкой/ }).click()
  await m.locator('.sheetbox .dtlink').waitFor()
  const url = (await m.locator('.sheetbox .dtlink').textContent()).match(/https?:\S+brief=\S+/)[0]
  await m.screenshot({ path: `${shots}/tz-2-mop-ssylka.png` })
  await m.locator('.sheetbox .x').click()
  await m.locator('.dtdeal .dtrow', { hasText: 'Школа' }).waitFor()
  assert.strictEqual((await bxCalls()).length, before, 'постановка задачи в Битрикс не пишет')

  // 2. Клиент: ссылка без входа и без Telegram, казахский, шесть шагов кнопками, фото стены
  const cctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const c = await cctx.newPage()
  await c.route('https://fonts.googleapis.com/**', r => r.fulfill({ body: '', contentType: 'text/css' }))
  await c.goto('http://127.0.0.1:4173/?' + url.split('?')[1])
  await c.locator('.cbcard h2', { hasText: 'Что за объект?' }).waitFor()
  assert.match(await c.locator('.cbhead').textContent(), /Школа: коридоры и столовая · 1 из 6/)
  assert.strictEqual(await c.locator('nav').count(), 0, 'клиенту приложение не показываем')
  await c.locator('.cbopts button', { hasText: 'Школа' }).click()
  await c.getByRole('button', { name: 'Дальше' }).click()
  await c.locator('.cbopts button', { hasText: 'Внутри' }).click(); await c.locator('.cbfield input').fill('коридор 24 × 3 м')
  await c.getByRole('button', { name: 'Дальше' }).click()
  await c.locator('.cbopts button', { hasText: 'Дети' }).click()
  await c.getByRole('button', { name: 'Дальше' }).click()
  await c.locator('.cbopts button', { hasText: 'Графика' }).click(); await c.locator('.cbopts button', { hasText: 'Энергия' }).click()
  await fits(c, 'бриф клиента')
  await c.screenshot({ path: `${shots}/tz-3-klient-brif.png` })
  await c.locator('.cblang button', { hasText: 'ҚАЗ' }).click()
  await c.locator('.cbcard h2', { hasText: 'Қандай стиль ұнайды?' }).waitFor()
  await c.screenshot({ path: `${shots}/tz-3b-klient-brif-kaz.png` })
  await c.locator('.cblang button', { hasText: 'RU' }).click()
  await c.getByRole('button', { name: 'Дальше' }).click()
  await c.locator('.cbopts button', { hasText: 'Тёплые' }).click(); await c.locator('.cbfield input').first().fill('Космос и планеты')
  await c.getByRole('button', { name: 'Дальше' }).click()
  await c.locator('.cbpic.add input').setInputFiles({ name: 'stena.png', mimeType: 'image/png', buffer: PNG })
  await c.locator('.cbpic.ok').waitFor()
  await c.locator('.cbfield input').first().fill('завуч Айгерим')
  await c.screenshot({ path: `${shots}/tz-4-klient-foto.png` })
  await c.getByRole('button', { name: 'Отправить' }).click()
  await c.locator('.cbdone').waitFor()
  await c.screenshot({ path: `${shots}/tz-5-klient-spasibo.png` })

  // 3. Дизайнер: «Сегодня», доска со сроком, карточка — ТЗ МОП, бриф клиента, материалы
  const d = await open(b, 7100)
  await tab(d, 'Дизайн')
  await d.locator('.dttoday').waitFor()
  await d.locator('.dtback .dtrow', { hasText: 'Школа' }).waitFor()      // клиент заполнил бриф — «Ответили»
  assert.match(await d.locator('.dtstage.new .dtrow').first().textContent(), /Школа.*эскиз к.*бриф клиента ✓.*материалы 4.*5 дней/)
  await fits(d, 'место дизайнера')
  await d.screenshot({ path: `${shots}/tz-6-dizainer-segodnya.png`, fullPage: true })
  await d.locator('.dtstage.new .dtrow', { hasText: 'Школа' }).click()
  const ds = d.locator('.sheetbox')
  await ds.locator('.dtstrip .dtthumb').nth(3).waitFor()
  assert.match(await ds.locator('.dtbox').first().textContent(), /ТЗ от МОП · Ануар.*Дети.*Графика.*Энергия.*Без чёрного/)
  assert.match(await ds.locator('.dtbox').nth(1).textContent(), /Бриф клиента.*Школа, детский сад.*коридор 24 × 3 м.*Космос и планеты.*завуч Айгерим/)
  await d.waitForTimeout(400)
  await fits(d, 'карточка задачи')
  await d.screenshot({ path: `${shots}/tz-7-dizainer-kartochka.png` })
  // «Вопрос МОП» — задача уходит в «Сбор информации»
  await ds.getByRole('button', { name: 'Вопрос МОП' }).click()
  await ds.locator('.dtbox textarea').fill('Логотип есть в векторе? Пришлите файлом.')
  await ds.getByRole('button', { name: 'Спросить' }).click()
  await ds.locator('.dtmsg.ask', { hasText: 'Логотип есть в векторе' }).waitFor()
  await d.waitForFunction(() => document.querySelector('.sheetbox select')?.value === 'info')
  await ds.locator('.mbody').evaluate(e => e.scrollTo(0, e.scrollHeight)); await d.waitForTimeout(300)
  await d.screenshot({ path: `${shots}/tz-7b-dizainer-kartochka-niz.png` })
  await ds.locator('.x').click()

  // 4. МОП: строка в «Сегодня», ответ из карточки сделки возвращает задачу в работу
  await m.reload()
  const q = m.locator('.qrow', { hasText: 'спрашивает' })
  await q.waitFor()
  assert.match(await q.textContent(), /№ 1601.*дизайнер Малика спрашивает: Логотип есть в векторе/)
  await m.screenshot({ path: `${shots}/tz-8-mop-segodnya.png` })
  await q.locator('.qmain').click()
  const ask = m.locator('.dtdeal .dtask')
  await ask.waitFor()
  assert.match(await m.locator('.dtdeal .dtsub').textContent(), /клиент заполнил бриф/)
  await ask.locator('textarea').fill('Да, отправил в материалы.')
  await ask.scrollIntoViewIfNeeded(); await m.waitForTimeout(300)
  await m.screenshot({ path: `${shots}/tz-9-mop-vopros.png` })
  await ask.getByRole('button', { name: 'Ответить' }).click()
  await ask.waitFor({ state: 'detached' })
  assert.match(await m.locator('.dtdeal .dtrow', { hasText: 'Школа' }).textContent(), /Малика.*Взято в работу/)
  // у дизайнера — «Ответили»
  await d.getByRole('button', { name: 'Обновить' }).click()
  await d.locator('.dtback .dtrow', { hasText: 'Школа' }).waitFor()
  assert.match(await d.locator('.dtstage.work .dtrow').first().textContent(), /Школа/)
  // 5. HEAD 28.11: срок прошёл — у дизайнера карточка горит, на Пульте строка «Дизайн просрочен» со списком
  execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qAtc "UPDATE design_tasks SET deadline = current_date - 2 WHERE deal_id = 1601"`)
  await d.getByRole('button', { name: 'Обновить' }).click()
  await d.locator('.dtrow', { hasText: 'просрочено' }).first().waitFor()
  await d.screenshot({ path: `${shots}/sroki-dizainer.png` })
  const hp = await open(b, 1000)
  const late = hp.locator('.qrow', { hasText: 'Дизайн просрочен: 1' })
  await late.click()
  await hp.locator('.asklist button', { hasText: /№ 1601 · Малика, 2 дн\. · .*Школа/ }).waitFor()
  await late.scrollIntoViewIfNeeded()
  await hp.screenshot({ path: `${shots}/sroki-pult.png` })
  await b.close()
  console.log('OK: «Нужен дизайн» одним экраном → бриф клиента по ссылке → «Сегодня» и карточка дизайнера → вопрос МОП и ответ')
})().catch(e => { console.error('FAIL', e.message); process.exit(1) })

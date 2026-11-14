// Сквозной тест «Оплата клиента» (HEAD 10.11): МОП вносит оплату в карточке сделки с фото чека → оплата «на сверке»,
// «Поступило» и «Долг» считает приложение по журналу; HEAD видит её в пульсе и «Проверке», ✓ сверяет, ✕ отменяет.
// «Дата и чек»: оплата из поля сделки без даты заменяется оплатой с датой и чеком. Итоги в Битрикс без ARTGAME_PAY_PUSH не пишутся. API — e2e/fake_api.py на пустой базе (Битрикс — ответы tests/test_bx.py).
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const bxCalls = async () => (await fetch(API + '/_e2e/bx_calls')).json()
const shots = process.env.SHOTS || '/var/tmp'
const CHEK = __dirname + '/chek.png'
const PNG = 'data:image/png;base64,' + require('fs').readFileSync(CHEK).toString('base64')
// «Команда» по отделам (HEAD 11.11): раскрыть отдел и человека
const person = async (h, name) => {
  const r = h.locator('.person', { hasText: name }).first()
  await h.locator('.dept').first().waitFor()
  if (!(await r.locator('.pedit').count())) {
    if (!(await r.count())) await h.locator('.dept', { hasText: name }).first().locator('.head').click()
    await h.locator('.prow', { hasText: name }).first().click()
  }
  await r.locator('.pedit').waitFor()
  return r
}
const today = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Almaty' })

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 800 } })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.route('https://fonts.googleapis.com/**', r => r.fulfill({ body: '', contentType: 'text/css' }))
  p.on('dialog', dl => dl.accept())
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
// На ширине iPhone ничего не вылезает вбок (HEAD 09.11: переносы и обрезки — первое, что видно)
const fits = async (p, what) => assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${what}: страница шире экрана`)
const noFin03 = async () => assert.ok(!(await bxCalls()).some(c => Object.keys(c.params.fields || {}).some(k => k.startsWith('UF_CRM_ARTGAME_FIN03_'))),
  'без ARTGAME_PAY_PUSH итоги в Битрикс не пишутся')

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  await fetch(API + '/_e2e/consts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ vat: '16' }) })
  const m = await call(6000, '/register', { full_name: 'Ануар', phone: '+7 701 111 22 33' })
  await call(1000, `/people/${m.id}`, { role_code: 'mop', zones: ['sales'], bitrix_user_id: 4565 })

  // МОП: карточка сделки → шаг «Оплата»: оплат нет, долг — вся сумма
  const p = await open(b, 6000)
  await tab(p, 'Сделки')
  await p.locator('.chips.scroll button', { hasText: 'Все' }).click()
  await p.locator('.stage .qrow', { hasText: '№ 1601' }).click()
  await p.locator('.hero .steps').waitFor()
  await p.locator('.hero .steps > div', { hasText: 'Оплата' }).click()
  const pay = p.locator('.card', { has: p.locator('h3', { hasText: /^Оплата$/ }) })
  await pay.waitFor()
  assert.match(await pay.locator('.kv').textContent(), /Поступило—.*Долг589\s250\s₸/)
  await pay.locator('text=Оплат по сделке ещё нет.').waitFor()
  await fits(p, 'шаг «Оплата»')
  await p.screenshot({ path: `${shots}/pay-panel.png`, fullPage: true })

  // «Внести оплату»: без суммы и чека не отправить; счёт — кнопками, «История» не предлагается
  await pay.getByRole('button', { name: '+ Внести оплату' }).click()
  const s = p.locator('.sheetbox')
  await s.locator('.mhead', { hasText: 'Внести оплату' }).waitFor()
  // ИП Артамонов — временно, до 31.12.2026 (HEAD 11.11); счёт не подставляется — выбирают сами
  assert.deepStrictEqual(await s.locator('.chips button').allTextContents(), ['Kaspi ИП Яковлев', 'Наличные', 'Переводы HEAD', 'ИП Артамонов'])
  assert.strictEqual(await s.locator('.chips button.on').count(), 0, 'счёт не выбран заранее')
  await s.locator('text=Выберите счёт, куда пришли деньги.').waitFor()
  await fits(p, 'окно без выбранного счёта')
  await p.waitForTimeout(300); await p.screenshot({ path: `${shots}/pay-sheet-empty.png` })
  assert.strictEqual(await s.locator('input[type=date]').inputValue(), today(), 'дата — сегодня')
  await s.locator('input[placeholder="Сумма, ₸"]').fill('300 000')
  assert.ok(await s.getByRole('button', { name: 'Внести 300 000 ₸' }).isDisabled(), 'без чека не отправить')
  await s.locator('.chips button', { hasText: 'Kaspi ИП Яковлев' }).click()
  await s.locator('input[placeholder^="Комментарий"]').fill('аванс 50%')
  await s.locator('.receipt input').first().setInputFiles(CHEK)
  await s.locator('.receipt img').waitFor()
  await fits(p, 'окно «Внести оплату»')
  await p.waitForTimeout(300); await p.screenshot({ path: `${shots}/pay-sheet.png` })
  await s.getByRole('button', { name: 'Внести 300 000 ₸' }).click()
  await p.locator('.toast', { hasText: 'Оплата внесена' }).waitFor()

  // «Поступило» и «Долг» — сразу по журналу; оплата «на сверке» у HEAD
  await pay.locator('.kv', { hasText: /Поступило300\s000\s₸Долг289\s250\s₸/ }).waitFor()
  assert.match(await pay.locator('.paylist').textContent(), /300\s000\s₸ Kaspi ИП Яковлев\d+ нояб\. · Ануар · чекна сверке/)
  await pay.locator('text=На сверке у HEAD: 300 000 ₸ (уже в «Поступило»).').waitFor()
  await fits(p, 'оплата внесена')
  await p.screenshot({ path: `${shots}/pay-done.png`, fullPage: true })
  let check = await call(1000, '/fin/payments/check')
  assert.strictEqual(check.length, 1)
  assert.deepStrictEqual([check[0].deal_id, check[0].amount, check[0].account_title, check[0].author, check[0].note, !!check[0].receipt_url],
    [1601, 300000, 'Kaspi ИП Яковлев', 'Ануар', '1601 · КАФЕ — АСТАНА · внёс Ануар · аванс 50%', true])
  await noFin03()

  // МОП не сверяет сам и не видит сверку
  assert.strictEqual((await fetch(API + '/fin/payments/check', { headers: { 'X-Telegram-Init-Data': sign(6000) } })).status, 403)

  // HEAD: в пульсе «Ждёт вашего решения» → «Проверка» → ✓
  const h = await open(b, 1000)
  const ask = h.locator('.qrow', { hasText: 'Оплаты клиентов на сверку: 1' })
  await ask.waitFor()
  assert.match(await ask.textContent(), /на 300\s000\s₸ · сверить чек и выписку/)
  assert.match(await h.locator('.pulse-kpi').textContent(), /1на проверке/)
  await fits(h, 'пульс HEAD')
  await h.screenshot({ path: `${shots}/head-pulse-pay.png` })
  await ask.click()
  const box = h.locator('.card', { has: h.locator('h2', { hasText: 'Оплаты клиентов на сверку' }) })
  await box.locator('.row', { hasText: 'сделка № 1601' }).waitFor()
  assert.match(await box.locator('.row').first().textContent(), /300\s000\s₸ · сделка № 1601.*Kaspi ИП Яковлев · КАФЕ — АСТАНА · внёс Ануар · аванс 50% · чек/)
  await fits(h, '«Проверка» HEAD')
  await box.scrollIntoViewIfNeeded(); await h.screenshot({ path: `${shots}/head-pay-check.png` })
  await box.locator('.row', { hasText: 'сделка № 1601' }).getByRole('button', { name: '✓' }).click()
  await box.locator('text=Всё сверено').waitFor()
  assert.deepStrictEqual(await call(1000, '/fin/payments/check'), [])

  // после ✓ в карточке нет «на сверке», «Поступило» то же
  let full = await call(6000, '/bx/deals/1601/full?fresh=1')
  assert.deepStrictEqual([full.pay.received, full.pay.debt, full.pay.on_check, full.pay.items[0].on_check], [300000, 289250, 0, false])

  // ✕: ошибочная оплата отменяется, «Поступило» уменьшается обратно, строка остаётся зачёркнутой
  const r = await call(6000, '/bx/deals/1601/payment', { client_uid: '0b6c5a8e-3f0e-4b8a-9d55-1f2a3b4c5d6e', amount: 50000, op_date: today(), account: 'cash', receipt: PNG })
  full = await call(6000, '/bx/deals/1601/full?fresh=1')
  assert.deepStrictEqual([full.pay.received, full.pay.on_check], [350000, 50000])
  await h.reload()
  await tab(h, 'Проверка')
  await box.locator('.row', { hasText: '50 000 ₸' }).getByRole('button', { name: '✕' }).click()
  await box.locator('text=Всё сверено').waitFor()
  full = await call(6000, '/bx/deals/1601/full?fresh=1')
  assert.deepStrictEqual([full.pay.received, full.pay.debt, full.pay.items.find(x => x.id === r.row.id).status], [300000, 289250, 'cancelled'])
  await p.reload()
  await tab(p, 'Сделки')
  await p.locator('.chips.scroll button', { hasText: 'Все' }).click()
  await p.locator('.stage .qrow', { hasText: '№ 1601' }).click()
  await p.locator('.hero .steps > div', { hasText: 'Оплата' }).click()
  await pay.locator('.paylist .row', { hasText: 'отменено HEAD' }).waitFor()
  await fits(p, 'отменённая оплата')
  await p.screenshot({ path: `${shots}/pay-cancelled.png`, fullPage: true })
  await noFin03()

  // «Вносит оплаты клиентов» (HEAD 10.11, Анна): HEAD ставит галочку в «Команде» → у Главного художника вкладка «Оплаты»:
  // сделка по названию или номеру, любая (не своя), оплата задним числом — в «Историю»
  const a = await call(7000, '/register', { full_name: 'Анна' })
  await call(1000, `/people/${a.id}`, { role_code: 'lead_artist', zones: ['mural'] })
  const an0 = await open(b, 7000)
  await an0.locator('nav button').first().waitFor()
  assert.ok(!(await an0.locator('nav button', { hasText: 'Оплаты' }).count()), 'без галочки вкладки нет')
  await an0.context().close()
  await h.reload()
  await tab(h, 'Команда')
  await (await person(h, 'Анна')).locator('label', { hasText: 'Вносит оплаты клиентов' }).locator('input').click()
  await h.waitForFunction(id => fetch('/api/people', { headers: { 'X-Telegram-Init-Data': window.Telegram.WebApp.initData } })
    .then(r => r.json()).then(l => l.find(x => x.id === id)?.pays), a.id)
  const an = await open(b, 7000)
  await tab(an, 'Оплаты')
  await an.locator('input[placeholder="№ сделки или название"]').fill('кафе')
  await an.getByRole('button', { name: 'Найти' }).click()
  await an.locator('.qrow', { hasText: '№ 1601' }).waitFor()
  assert.strictEqual(await an.locator('.qrow', { hasText: '№ 1647' }).count(), 1, 'и дизайн, и продажи')
  await fits(an, 'поиск «Оплат»')
  await an.screenshot({ path: `${shots}/pays-find.png` })
  await an.locator('input[placeholder="№ сделки или название"]').fill('1590')
  await an.getByRole('button', { name: 'Найти' }).click()
  const desk = an.locator('.card', { has: an.locator('h3', { hasText: '№ 1590' }) })
  await desk.waitFor()
  assert.match(await desk.locator('.kv').textContent(), /Сумма2\s900\s000\s₸Поступило—Долг2\s900\s000\s₸/)
  await desk.getByRole('button', { name: '+ Внести оплату' }).click()
  const s2 = an.locator('.sheetbox')
  await s2.locator('input[placeholder="Сумма, ₸"]').fill('2900000')
  await s2.locator('input[type=date]').fill('2026-10-15')
  await s2.locator('text=Оплата до ноября уйдёт в «Историю»').waitFor()
  assert.deepStrictEqual(await s2.locator('.chips button').allTextContents(), ['Наличные'], 'счёт не выбирается: «История», наличные — отметкой')
  await s2.locator('.receipt input').first().setInputFiles(CHEK)
  await s2.locator('.receipt img').waitFor()
  await fits(an, 'оплата задним числом')
  await an.waitForTimeout(300); await an.screenshot({ path: `${shots}/pays-hist-sheet.png` })
  await s2.getByRole('button', { name: 'Внести 2 900 000 ₸' }).click()
  await an.locator('.toast', { hasText: 'Оплата внесена' }).waitFor()
  await desk.locator('.kv', { hasText: /Поступило2\s900\s000\s₸Долг—/ }).waitFor()
  assert.match(await desk.locator('.paylist').textContent(), /2\s900\s000\s₸ История \(до ноября\)15 окт\. · Анна · чекна сверке/)
  await fits(an, '«Оплаты» после оплаты')
  await an.screenshot({ path: `${shots}/pays-done.png`, fullPage: true })
  check = await call(1000, '/fin/payments/check')
  assert.deepStrictEqual(check.map(x => [x.deal_id, x.amount, x.account_title, x.author]), [[1590, 2900000, 'История (до ноября)', 'Анна']])

  // «Дата и чек» (10.11): Анна вносила оплату в «Поступление 1» без даты — указывает дату и чек, «Поступило» не задваивается
  await fetch(API + '/_e2e/deal/1700', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ UF_CRM_ARTGAME_FIN03_PAY1_AMOUNT: '1200000|KZT', UF_CRM_ARTGAME_FIN03_PAY1_DATE: '' }) })
  await an.locator('input[placeholder="№ сделки или название"]').fill('1700')
  await an.getByRole('button', { name: 'Найти' }).click()
  const d17 = an.locator('.card', { has: an.locator('h3', { hasText: '№ 1700' }) })
  await d17.waitFor()
  assert.match(await d17.locator('.kv').textContent(), /Поступило1\s200\s000\s₸Долг1\s200\s000\s₸/)
  assert.match(await d17.locator('.paylist').textContent(), /1\s200\s000\s₸ из поля сделкибез даты/)
  await d17.getByRole('button', { name: '+ Внести оплату' }).click()
  await an.locator('.sheetbox', { hasText: 'В сделке есть оплата без даты: 1 200 000 ₸' }).waitFor()   // подсказка: не задвоить
  await an.locator('.sheetbox').getByRole('button', { name: 'Отмена' }).click()
  await fits(an, 'оплата без даты')
  await an.screenshot({ path: `${shots}/pays-undated.png`, fullPage: true })
  await d17.getByRole('button', { name: 'Дата и чек' }).click()
  const s3 = an.locator('.sheetbox')
  await s3.locator('text=из поля «Поступление 1» без даты').waitFor()
  assert.strictEqual(await s3.locator('input[placeholder="Сумма, ₸"]').inputValue(), '1200000')
  await s3.locator('input[type=date]').fill('2026-11-04')
  await s3.locator('.chips button', { hasText: 'Kaspi ИП Яковлев' }).click()
  await s3.locator('.receipt input').first().setInputFiles(CHEK)
  await s3.locator('.receipt img').waitFor()
  await fits(an, '«Дата и чек»')
  await an.waitForTimeout(300); await an.screenshot({ path: `${shots}/pays-slot-sheet.png` })
  await s3.getByRole('button', { name: 'Сохранить 1 200 000 ₸' }).click()
  await an.locator('.toast', { hasText: 'Дата и чек сохранены' }).waitFor()
  await d17.locator('.paylist', { hasText: 'Анна' }).waitFor()
  assert.match(await d17.locator('.kv').textContent(), /Поступило1\s200\s000\s₸Долг1\s200\s000\s₸/)   // не 2 400 000
  const list17 = await d17.locator('.paylist').textContent()
  assert.match(list17, /1\s200\s000\s₸ Kaspi ИП Яковлев4 нояб\. · Анна · чекна сверке/)
  assert.ok(!/из поля сделки/.test(list17) && !(await d17.getByRole('button', { name: 'Дата и чек' }).count()), 'поле заменено')
  await an.screenshot({ path: `${shots}/pays-slot-done.png`, fullPage: true })
  // наличные (HEAD 10.11): без фото чека можно, HEAD сверит сам
  await d17.getByRole('button', { name: '+ Внести оплату' }).click()
  const s4 = an.locator('.sheetbox')
  await s4.locator('input[placeholder="Сумма, ₸"]').fill('50000')
  await s4.locator('.chips button', { hasText: 'Kaspi ИП Яковлев' }).click()
  assert.ok(await s4.getByRole('button', { name: 'Внести 50 000 ₸' }).isDisabled(), 'Kaspi без фото — нельзя')
  await s4.locator('.chips button', { hasText: 'Наличные' }).click()
  await s4.locator('text=Без фото HEAD сверит сам').waitFor()
  await fits(an, 'наличные без фото')
  await an.waitForTimeout(300); await an.screenshot({ path: `${shots}/pays-cash.png` })
  await s4.getByRole('button', { name: 'Внести 50 000 ₸' }).click()
  await an.locator('.toast', { hasText: 'Оплата внесена' }).waitFor()
  await d17.locator('.paylist', { hasText: 'без чека' }).waitFor()
  assert.match(await d17.locator('.paylist').textContent(), /50\s000\s₸ Наличные\d+ нояб\. · Анна · без чекана сверке/)
  check = await call(1000, '/fin/payments/check')
  assert.deepStrictEqual(check.map(x => [x.deal_id, x.amount, x.op_date]), [[1590, 2900000, '2026-10-15'], [1700, 1200000, '2026-11-04'], [1700, 50000, today()]])
  assert.match(check[1].note, /вместо «Поступление 1» без даты/)
  assert.strictEqual(check[2].receipt_url, null)
  await fetch(API + '/_e2e/deal/1700', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ UF_CRM_ARTGAME_FIN03_PAY1_AMOUNT: null, UF_CRM_ARTGAME_FIN03_PAY1_DATE: null }) })
  await noFin03()
  console.log('OK: оплата с чеком из карточки, «Поступило» и долг по журналу, сверка HEAD ✓/✕ в пульсе и «Проверке», «Оплаты» по галочке и задним числом, «Дата и чек» к оплате без даты без двойного счёта, наличные без фото, без записи итогов в Битрикс')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

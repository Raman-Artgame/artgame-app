// МОП вводит всё в приложении (HEAD 25.11 «давай делаем»): заявка по звонку с проверкой дубля, клиент и реквизиты,
// подписанный договор. API — подменённый Битрикс (fake_api), экран — vite preview :4173, ширина iPhone.
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
const noScroll = async p => assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'нет прокрутки вбок')

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.route('https://fonts.googleapis.com/**', r => r.fulfill({ body: '', contentType: 'text/css' }))
  await p.goto('http://127.0.0.1:4173/')
  return p
}
async function tab(p, name) {
  const nav = p.locator('nav')
  await nav.locator('button').first().waitFor()
  const re = new RegExp(`^${name}\\s*\\d*$`)
  if (await nav.getByRole('button', { name: re }).waitFor({ timeout: 1500 }).then(() => true, () => false)) return nav.getByRole('button', { name: re }).click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const m = await call(6000, '/register', { full_name: 'Ануар', phone: '+7 701 111 22 33' })
  await call(1000, `/people/${m.id}`, { role_code: 'mop', zones: ['sales'], bitrix_user_id: 4565 })
  const p = await open(b, 6000)

  // 1. Заявка по звонку: «+ Заявка» в «Лидах»; номер уже есть — сначала показываем, чей это лид
  await tab(p, 'Лиды')
  await p.getByRole('button', { name: '+ Заявка' }).click()
  const sh = p.locator('.sheetbox')
  await sh.locator('.newlead').waitFor()
  assert.deepStrictEqual(await sh.locator('.chips').first().locator('button').allTextContents(), ['Звонок', 'Сайт', 'Сарафан', 'Холодная база'], 'WhatsApp руками не выбирается')
  await sh.locator('label', { hasText: 'Имя клиента' }).locator('input').fill('Айгерим')
  await sh.locator('label', { hasText: 'Телефон' }).locator('input').fill('8 701 555 44 33')
  await sh.locator('.chips button', { hasText: 'Астана' }).click()
  await sh.locator('textarea').fill('Кафе на Кенесары, стена 40 м², хотят до Нового года')
  await noScroll(p)
  await p.screenshot({ path: `${shots}/mopvvod-1-zayavka.png` })
  await sh.getByRole('button', { name: 'Завести заявку' }).click()
  await sh.getByText('Этот номер уже есть в Битриксе').waitFor()
  assert.match(await sh.textContent(), /Лид № 3001 · Дана/)
  await p.screenshot({ path: `${shots}/mopvvod-2-dubl.png` })
  assert.ok(!(await bxCalls()).some(x => x.method === 'crm.lead.add'), 'дубль — без записи')
  await sh.getByRole('button', { name: 'Назад' }).click()
  await sh.locator('label', { hasText: 'Телефон' }).locator('input').fill('+7 702 333 22 11')
  await sh.getByRole('button', { name: 'Завести заявку' }).click()
  await p.locator('.sheetbox').waitFor({ state: 'detached' })
  const add = (await bxCalls()).find(x => x.method === 'crm.lead.add')
  assert.strictEqual(add.params.fields.SOURCE_ID, 'CALL')
  assert.strictEqual(add.params.fields.ASSIGNED_BY_ID, 4565)
  await p.getByText('Айгерим').first().waitFor()   // открылась карточка нового лида

  // 2. Клиент и реквизиты сделки 1601 (ТОО «Ромашка»): БИН, подписант, банк → в Битрикс, договор возьмёт сам
  await tab(p, 'Сделки')
  await p.locator('.chips.scroll button', { hasText: 'Все' }).click()
  await p.locator('.stage .qrow', { hasText: '№ 1601' }).click()
  await p.locator('.hero .steps').waitFor()
  await p.locator('.hero .morebtn').click()
  await p.locator('.hero').getByRole('button', { name: 'Клиент и реквизиты', exact: true }).click()
  const cs = p.locator('.sheetbox .client')
  await cs.waitFor()
  assert.strictEqual(await cs.locator('.seg button:not(.ghost)').textContent(), 'ТОО')
  assert.strictEqual(await cs.locator('label', { hasText: 'Название ТОО' }).locator('input').inputValue(), 'ТОО «Ромашка»')
  await cs.locator('label', { hasText: 'БИН' }).locator('input').fill('123456789012')
  await cs.locator('label', { hasText: 'Кто подписывает' }).locator('input').fill('Сидоров Самат')
  await cs.locator('label', { hasText: 'Банк' }).locator('input').fill('АО «Kaspi Bank»')
  await cs.locator('label', { hasText: 'БИК' }).locator('input').fill('caspkzka')
  await cs.locator('label', { hasText: 'ИИК' }).locator('input').fill('KZ12 3456 7890 1234 5678')
  await noScroll(p)
  await p.screenshot({ path: `${shots}/mopvvod-3b-bank.png` })
  await cs.locator('.seg').scrollIntoViewIfNeeded()
  await p.waitForTimeout(300)
  await p.screenshot({ path: `${shots}/mopvvod-3-rekvizity.png` })
  await cs.getByRole('button', { name: 'Сохранить' }).click()
  await p.locator('.toast', { hasText: 'Записано в Битрикс' }).waitFor()
  console.log('toast:', await p.locator('.toast').textContent())
  assert.match(await p.locator('.toast').textContent(), /новые реквизиты, банк/)
  const calls = await bxCalls()
  const rq = calls.find(x => x.method === 'crm.requisite.add').params.fields
  assert.strictEqual(rq.PRESET_ID, 3); assert.strictEqual(rq.RQ_BIN, '123456789012'); assert.strictEqual(rq.RQ_CEO_NAME, 'Сидоров Самат')
  assert.strictEqual(calls.find(x => x.method === 'crm.requisite.bankdetail.add').params.fields.RQ_IIK, 'KZ123456789012345678')

  // 2б. «Заполнить недостающее» → окно «Карточка сделки» по шагам: нехватающее отмечено «нужно», всё заполняется здесь
  await p.locator('.fillbar .fb-go').click()
  const fs = p.locator('.sheetbox .fillform')
  await fs.waitFor()
  await fs.locator('label', { hasText: 'Куратор ГИП' }).waitFor()
  const txt = await fs.textContent()
  assert.ok(!txt.includes('«Заполнить карточку» →') && !txt.includes('Ответственный исполнитель') && !txt.includes('Художники'), 'старого нет')
  assert.deepStrictEqual(await fs.locator('h3.fillsec').evaluateAll(h => h.map(x => x.firstChild.textContent)), ['Клиент и объект', 'Договор', 'В работе'])
  await noScroll(p)
  await p.screenshot({ path: `${shots}/mopvvod-5-kartochka.png` })
  await p.setViewportSize({ width: 390, height: 2300 }); await p.waitForTimeout(300)
  await p.screenshot({ path: `${shots}/mopvvod-5-kartochka-full.png` })
  await p.setViewportSize({ width: 390, height: 844 })
  await p.locator('.sheetbox button.x').click()
  await p.locator('.sheetbox').waitFor({ state: 'detached' })

  // 3. Подписанный договор: шаг «Договор» → «Загрузить подписанный договор» → поле сделки
  await p.locator('.hero .steps > div', { hasText: 'Договор' }).click()
  const up = p.locator('.card.signed')
  await up.waitFor()
  await noScroll(p)
  await up.scrollIntoViewIfNeeded()
  await p.screenshot({ path: `${shots}/mopvvod-4-dogovor.png` })
  await up.locator('input[type=file]').setInputFiles({ name: 'скан.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 подписано') })
  await p.locator('.toast', { hasText: 'Подписанный договор в сделке' }).waitFor()
  const upd = (await bxCalls()).filter(x => x.method === 'crm.deal.update').pop()
  assert.strictEqual(upd.params.fields.UF_CRM_1753202391, 'файл')
  console.log('mopvvod ok')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

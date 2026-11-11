// Сквозной тест правок HEAD 08.11: кабинет саппорта (меню, расходы только такси/докупка, «Как стать художником», без калькулятора
// в «Выезде»), «Продакшн» Главного художника (рилс → МЕДИА/Отчёты) и утверждение HEAD (→ МЕДИА/Продакшн, счётчик в Пульте).
// API — e2e/fake_api.py (Диск и Битрикс подменены), см. app/README.md.
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
const psql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "${q}"`)

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 780 } })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  p.on('dialog', dl => dl.accept('темно'))
  await p.goto('http://127.0.0.1:4173/')
  await p.locator('nav').waitFor()
  return p
}
const navText = async p => (await p.locator('nav button').allTextContents()).map(t => t.replace(/\d+$/, ''))
async function tab(p, name) {
  const nav = p.locator('nav')
  const btn = nav.getByRole('button', { name, exact: true })
  if (await btn.waitFor({ timeout: 2000 }).then(() => true, () => false)) return btn.click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  await call(1000, '/_e2e/consts', { 'pay.reels': '5000', 'pay.reels.max': '10', 'norm.mural.medium': '10', 'norm.role.support': '0,5', 'shift.hours': '10' })
  const ids = {}
  for (const [tg, name, role, zones] of [[2000, 'Саппорт Нурлан', 'support', ['mural']], [3000, 'Главный Ержан', 'lead_artist', ['mural']],
    [4000, 'Оператор Аян', 'print_operator', ['print']]]) {
    ids[tg] = (await call(tg, '/register', { full_name: name })).id
    await call(1000, `/people/${ids[tg]}`, { role_code: role, zones })
  }
  psql("INSERT INTO objects (id, title, city, bitrix_stage, level, area_m2, address) VALUES (731, 'Кафе e2e', 'Астана', 'UC_AV00QK', 'hard', 40, 'Кабанбай батыра 5') ON CONFLICT (id) DO NOTHING")

  // 1. Саппорт: меню без склада и «Объектов», промо объекта со сложностью из сделки, расходы — такси и докупка
  const s = await open(b, 2000)
  assert.deepStrictEqual(await navText(s), ['Смена', 'Расход', 'Проекты', 'Учёба', 'Кабинет', 'Чат'])
  await s.locator('.promo').getByText('Сложный').waitFor()
  await s.locator('.promo').getByText('Кабанбай батыра 5', { exact: false }).waitFor()
  await s.screenshot({ path: `${shots}/support-smena.png`, fullPage: true })
  await tab(s, 'Расход')
  await s.getByRole('button', { name: 'Отправить расход' }).waitFor()
  const opts = await s.locator('select').nth(1).locator('option').allTextContents()
  assert.deepStrictEqual(opts, ['Такси / доставка', 'Докупка на объект'], opts.join(','))
  // «Учёба» (HEAD 08.11): База знаний, Тест, Клиентам + ТБ и «Правила игры» (внутри — как стать художником); «Выезда» нет
  await tab(s, 'Учёба')   // «Правила игры» в «Учёбе» больше нет — только в «Кабинете» (HEAD 09.11)
  assert.ok(!(await s.locator('.place .chips button').allTextContents()).includes('Правила игры'))
  await tab(s, 'Кабинет')
  await s.locator('.dutyfold').getByRole('button', { name: 'Открыть' }).click()
  await s.getByText('Правила игры · Саппорт').waitFor()
  await s.getByText(/Что нужно для ступени/).waitFor()
  // Полная должностная (HEAD 08.11): требования, права, запрещено, политика; без источника — «черновик»
  await s.getByText('Требования', { exact: true }).waitFor()
  await s.getByText('Что запрещено').waitFor()
  await s.getByText('Политика ARTGAME — для всех').waitFor()
  await s.getByText('Публиковать фото и видео работ', { exact: false }).waitFor()
  assert.ok(await s.locator('.tag.draft').count() >= 1)
  await s.locator('.card.duty.forbid').scrollIntoViewIfNeeded()
  await s.screenshot({ path: `${shots}/support-zapreshcheno.png` })
  assert.strictEqual(await s.getByText('Чек-лист выезда').count(), 0)
  await s.screenshot({ path: `${shots}/support-pravila.png`, fullPage: true })
  await tab(s, 'Учёба')
  await s.getByRole('button', { name: 'ТБ', exact: true }).click()
  await s.getByText('ТБ на объекте').waitFor()
  await s.getByText('1,8 м').waitFor()
  await s.screenshot({ path: `${shots}/support-tb.png`, fullPage: true })
  await s.getByRole('button', { name: 'Учебник' }).click()
  await s.waitForFunction(() => !!document.querySelector('iframe.placeframe')?.contentWindow?.document.querySelector('#tabs'), null, { timeout: 20000 })
  const frame = s.frames().find(f => /\/api\/p\//.test(f.url()))
  assert.ok(/dark=1/.test(frame.url()) && /trip/.test(frame.url()))
  await frame.evaluate(() => { location.hash = '#trip' })
  await s.waitForTimeout(300)
  assert.notStrictEqual(await frame.evaluate(() => location.hash), '#trip')   // «Выезд» переехал в «Смену»
  await s.screenshot({ path: `${shots}/support-baza.png`, fullPage: true })

  await tab(s, 'Кабинет')   // «Правила игры» в «Кабинете» у всех (HEAD 08.11)
  await s.locator('.dutyfold').getByRole('button', { name: 'Открыть' }).click()
  await s.locator('.dutyfold').getByText('Что ты делаешь').waitFor()
  await s.screenshot({ path: `${shots}/kabinet-pravila.png`, fullPage: true })
  // «Написать обращение» (HEAD 08.11): саппорт пишет — HEAD отвечает в «Пульте» — ответ в «Кабинете»
  await s.getByRole('button', { name: 'Написать', exact: true }).click()
  await s.locator('.fbform').getByPlaceholder(/Где/).fill('Смена')
  await s.locator('.fbform textarea').fill('Фото не грузится на объекте')
  await s.locator('.fbform').getByRole('button', { name: 'Отправить' }).click()
  await s.locator('.fbrow', { hasText: 'Фото не грузится' }).getByText('отправлено').waitFor()
  const hp = await open(b, 1000)
  const fbc = hp.locator('.fb', { hasText: 'Обращения' })
  await fbc.locator('.fbrow', { hasText: 'Фото не грузится' }).waitFor()
  await fbc.locator('textarea').first().fill('Починили, обнови приложение')
  await hp.screenshot({ path: `${shots}/obrashcheniya-pult.png`, fullPage: true })
  await fbc.getByRole('button', { name: 'Готово' }).first().click()
  await hp.locator('.fb', { hasText: 'Обращения' }).waitFor({ state: 'detached' })
  await s.reload(); await tab(s, 'Кабинет')
  await s.locator('.fbans', { hasText: 'Починили' }).waitFor()
  await s.screenshot({ path: `${shots}/obrashchenie-kabinet.png`, fullPage: true })

  // 2. Оператор печати: склада нет
  const op = await open(b, 4000)
  assert.ok(!(await navText(op)).includes('Склад'))
  assert.deepStrictEqual(await navText(op), ['Смена', 'Расход', 'Проекты', 'Учёба', 'Кабинет', 'Чат'])
  await tab(op, 'Учёба')   // печать — как у художников: Учебник, Тест, Фотозадание, Клиентам + ТБ и «Правила игры»
  assert.deepStrictEqual(await op.locator('.place .chips button').allTextContents(), ['Учебник', 'Подготовка к печати', 'Клиентам', 'ТБ'])   // HEAD 09.11
  await tab(op, 'Кабинет')
  await op.locator('.dutyfold').getByRole('button', { name: 'Открыть' }).click()
  await op.getByText('Правила игры · Оператор печати').waitFor()
  await op.screenshot({ path: `${shots}/print-pravila.png`, fullPage: true })
  // «Мастерская» без проекта (HEAD 09.11): ТО принтера — без фото, оплата по часам
  await tab(op, 'Смена')
  await op.getByRole('button', { name: 'Мастерская · без проекта' }).click()
  await op.getByRole('button', { name: 'ТО принтера' }).click()
  await op.screenshot({ path: `${shots}/print-workshop.png` })
  await op.getByRole('button', { name: 'Начать смену в мастерской' }).click()
  await op.getByText('Мастерская · ТО принтера').first().waitFor()
  await op.locator('textarea').fill('Прочистка головы, тест-печать')
  await op.getByRole('button', { name: 'Закончить и отправить на проверку' }).click()
  await op.getByText(/ушла на проверку/).waitFor()

  // 2б. Две роли (HEAD 08.11, «Оба способа»): HEAD даёт оператору вторую роль «Саппорт» — «Я сейчас», роль смены по объекту, обе ставки
  await call(1000, `/people/${ids[4000]}`, { extra_roles: ['support'], zones: ['print', 'mural'] })
  await op.reload()
  await op.locator('.roleswitch').waitFor()
  await op.locator('.roleswitch button', { hasText: 'Саппорт' }).click()
  await op.waitForLoadState('load')
  await op.locator('.roleswitch button.on', { hasText: 'Саппорт' }).waitFor()
  await tab(op, 'Смена')
  await op.getByText('Роль на смене — по ней ставка').waitFor()
  await op.locator('.segf button', { hasText: 'Печать' }).click()   // объект печати — роль сама «Оператор печати»
  await op.locator('.chips button.on', { hasText: 'Оператор печати' }).waitFor()
  await op.locator('.segf button', { hasText: 'Роспись' }).click()
  await op.locator('.chips button.on', { hasText: 'Саппорт' }).waitFor()
  await op.screenshot({ path: `${shots}/dve-roli-smena.png`, fullPage: true })
  await tab(op, 'Кабинет')
  assert.strictEqual(await op.locator('.dutyfold').count(), 2)   // «Правила игры» обеих ролей
  await op.screenshot({ path: `${shots}/dve-roli-kabinet.png`, fullPage: true })
  await op.locator('.roleswitch button', { hasText: 'Оператор' }).click()
  await op.waitForLoadState('load')
  await op.locator('.roleswitch button.on', { hasText: 'Оператор' }).waitFor()

  // 3. Главный художник: «Продакшн» — рилс с объекта (большой файл идёт прямо в Google — здесь подменён)
  const l = await open(b, 3000)
  await l.route('https://upload.example/**', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'drvBIG00000077' }) }))
  await tab(l, 'Продакшн')
  await l.getByText('Материал с объекта').waitFor()
  await l.locator('.seg').getByRole('button', { name: 'Рилс' }).click()
  await l.getByText(/\+5\s000 ₸/).waitFor()
  await l.screenshot({ path: `${shots}/prod-zagruzka.png`, fullPage: true })
  await l.locator('label.photo input[type=file]').setInputFiles({ name: 'Рилс кафе.mp4', mimeType: 'video/mp4', buffer: Buffer.from('MP4-DATA') })
  await l.locator('.mitem', { hasText: 'Рилс кафе.mp4' }).getByText('у HEAD').waitFor()
  await l.screenshot({ path: `${shots}/prod-moe.png`, fullPage: true })

  // 4. HEAD: Пульт зовёт утвердить, «Продакшн» → «Утверждаю» → копия в МЕДИА/Продакшн
  const h = await open(b, 1000)
  await h.getByText('Материал с объектов на утверждение: 1').waitFor()
  await tab(h, 'Продакшн')
  await h.locator('.mitem', { hasText: 'Рилс кафе.mp4' }).waitFor()
  await h.screenshot({ path: `${shots}/prod-head.png`, fullPage: true })
  await h.getByRole('button', { name: 'Утверждаю' }).click()
  await h.getByText('Всё утверждено.').waitFor()
  const mine = await call(3000, '/media?scope=mine')
  assert.strictEqual(mine.items[0].review, 'approved')
  // саппорт видит утверждённое в карточке проекта
  assert.strictEqual((await call(2000, '/media?scope=object&object_id=731')).items.length, 1)
  // 5. Главный дизайнер (HEAD 10.11): «Продакшн → Медиа» — видео со всех объектов, скачать, сдать готовый рилс HEAD
  const dzId = (await call(7000, '/register', { full_name: 'Дизайнер Малика' })).id
  await call(1000, `/people/${dzId}`, { role_code: 'lead_designer', zones: ['design'] })
  psql(`INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by, status, media_type, review) VALUES (gen_random_uuid(), 731, 'media', 'Процесс кафе.mp4', 'video/mp4', 9000000, 'drvVID0000001', ${ids[3000]}, 'ready', 'video', 'pending')`)
  const dz = await open(b, 7000)
  await dz.route('https://upload.example/**', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'drvBIG00000078' }) }))
  await tab(dz, 'Продакшн')
  await dz.locator('.mitem', { hasText: 'Процесс кафе.mp4' }).waitFor()
  await dz.locator('.mitem', { hasText: 'Рилс кафе.mp4' }).waitFor({ state: 'detached', timeout: 1000 }).catch(() => {})
  await dz.screenshot({ path: `${shots}/prod-dizainer-media.png`, fullPage: true })
  await dz.getByRole('button', { name: '🎬 Загрузить готовый рилс' }).click()
  await dz.locator('.seg button:not(.ghost)', { hasText: 'Рилс' }).waitFor()
  await dz.locator('label.photo input[type=file]').setInputFiles({ name: 'Рилс дизайнера.mp4', mimeType: 'video/mp4', buffer: Buffer.from('MP4-DATA') })
  await dz.locator('.mitem', { hasText: 'Рилс дизайнера.mp4' }).getByText('у HEAD').waitFor()
  assert.ok((await call(1000, '/media?scope=review')).items.some(x => x.name === 'Рилс дизайнера.mp4'))
  // 6. Командировка в карточке проекта (HEAD 10.11): Главный художник ставит «Да, выезд» → пункты расходов, вносит проживание
  psql("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1700, 'Школа — Шымкент', 'Шымкент', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")   // синк сделки «Выполнение проекта»
  await tab(l, 'Проекты')
  await l.locator('.pcard', { hasText: '№1700' }).first().click()
  const trip = l.locator('.card.trip')
  await trip.getByRole('button', { name: 'Да, выезд' }).click()
  await trip.locator('.row', { hasText: 'Питание' }).waitFor()
  await trip.locator('.row', { hasText: 'Проживание' }).getByRole('button', { name: '+ сумма' }).click()
  await trip.getByPlaceholder('Сумма, ₸').fill('45000')
  await trip.getByPlaceholder(/Комментарий/).fill('3 ночи')
  await trip.locator('.receipt input').first().setInputFiles(__dirname + '/chek.png')
  await trip.locator('.receipt img').waitFor()
  await trip.getByRole('button', { name: 'Записать' }).click()
  await trip.locator('.row', { hasText: 'Проживание' }).getByText(/45\s000 ₸ · компании · Главный Ержан · 3 ночи · у HEAD/).waitFor()
  await trip.scrollIntoViewIfNeeded()
  await l.screenshot({ path: `${shots}/komandirovka.png` })
  const rv2 = await call(1000, '/review')
  assert.ok(rv2.expenses.some(x => +x.amount === 45000 && x.category_title.startsWith('Проживание')))
  console.log('OK: саппорт (меню, расходы, как стать художником, без калькулятора), продакшн и утверждение HEAD, медиа и рилс Главного дизайнера, командировка')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

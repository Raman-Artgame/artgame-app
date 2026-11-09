// Сквозной тест «Кабинеты команды» (HEAD 07.11): меню по ролям, «Сбор на объект», воронка «Дизайн РК», каталог референсов,
// Про проверяет Главного, своя ставка в «Мои». API — e2e/fake_api.py (Битрикс подменён), см. app/README.md.
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
  const ctx = await b.newContext({ viewport: { width: 390, height: 780 } })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  p.on('dialog', dl => dl.accept())
  await p.goto('http://127.0.0.1:4173/')
  await p.locator('nav').waitFor()
  return p
}
const navText = async p => (await p.locator('nav button').allTextContents()).map(t => t.replace(/\d+$/, ''))
async function tab(p, name) {
  const nav = p.locator('nav')
  const btn = nav.getByRole('button', { name, exact: true })
  if (await btn.waitFor({ timeout: 2000 }).then(() => true, () => false)) return btn.click()
  await nav.locator('button').last().click()   // «Ещё»
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  await call(1000, '/_e2e/consts', { 'pay.artist.shift': '15000', 'pay.artist.hour': '1500', 'pay.chief.shift': '20000', 'pay.chief.min_month': '150000',
    'shift.hours': '10', 'pay.design.lead.month': '300000', 'pay.design.unit_over': '10000', 'pay.design.catalog': '5000',
    'design.unit.xs': '0,5', 'design.unit.s': '1', 'design.unit.m': '2', 'design.unit.l': '4', 'design.unit.xl': '8' })
  const ids = {}
  for (const [tg, name, role, zones, bxu] of [[2000, 'Дана', 'artist', ['mural'], 0], [3000, 'Главный Ержан', 'lead_artist', ['mural'], 0],
    [4000, 'Про Айбек', 'artist_pro', ['mural'], 0], [7000, 'Главный дизайнер Алия', 'lead_designer', ['design'], 4565],
    [7100, 'Помощник Мира', 'designer_asst', ['design'], 4693]]) {
    ids[tg] = (await call(tg, '/register', { full_name: name })).id
    await call(1000, `/people/${ids[tg]}`, { role_code: role, zones, ...(bxu ? { bitrix_user_id: bxu } : {}) })
  }
  // объект в работе (на сервере их заводит синхронизация со сделками) — прямо в тестовую базу
  execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "INSERT INTO objects (id, title, city, bitrix_stage) VALUES (731, 'Кафе e2e', 'Астана', 'UC_AV00QK') ON CONFLICT (id) DO UPDATE SET bitrix_stage='UC_AV00QK'"`)
  const obj = (await call(3000, '/work/dict')).objects.find(o => o.id)
  assert.ok(obj, 'нужен активный объект')

  // 1. Меню по ролям (HEAD 08.11: «Объекты» влиты в «Проекты», склада у художника нет)
  const a = await open(b, 2000)
  assert.deepStrictEqual(await navText(a), ['Смена', 'Расход', 'Проекты', 'Учёба', 'Кабинет'])
  await tab(a, 'Расход')
  await a.getByRole('button', { name: 'Отправить расход' }).waitFor()
  assert.strictEqual(await a.getByRole('button', { name: 'Закупка на склад' }).count(), 0)
  await tab(a, 'Кабинет')
  await a.getByText('Моя ставка').waitFor()
  await a.getByText(/15\s000 ₸/).first().waitFor()
  await a.screenshot({ path: `${shots}/kab-artist-moi.png` })

  // 2. Главный художник: «Сбор и сдача» по шагам — взяли (счётчики) → вернули → сдать
  const l = await open(b, 3000)
  assert.deepStrictEqual(await navText(l), ['Сбор', 'Смена', 'Расход', 'Продакшн', 'Проверка', 'Проекты', 'Учёба', 'Кабинет'])
  await tab(l, 'Сбор')
  await l.getByText(obj.title).waitFor()
  await l.locator('.kitobj', { hasText: obj.title }).getByRole('button', { name: /Роспись/ }).click()
  await l.getByRole('button', { name: '+ цвет' }).click()
  const ar = l.locator('.kitrow2').first()
  await ar.locator('input').nth(0).fill('RAL 3020')
  await ar.locator('.stepper input').fill('5')
  await ar.getByRole('button', { name: 'больше' }).click()          // 5 → 6 кнопкой «+»
  await l.locator('.kitline', { hasText: 'Фасадная' }).locator('.stepper input').fill('12,5')
  await l.locator('.tap', { hasText: 'Стремянки' }).click()
  await l.locator('.chips button.on', { hasText: 'исправно' }).first().waitFor()   // состояние «взял» ставится само
  await l.screenshot({ path: `${shots}/kab-sbor.png`, fullPage: true })
  await l.getByRole('button', { name: 'Собрано → к возврату' }).click()
  await l.locator('.kitline', { hasText: 'Аэрозоль RAL 3020' }).locator('.stepper input').fill('2')
  await l.locator('.kitline', { hasText: 'Фасадная' }).locator('.stepper input').fill('2,5')
  await l.locator('.tap', { hasText: 'Стремянки' }).click()
  await l.locator('.chips button', { hasText: 'есть замечание' }).last().click()
  await l.screenshot({ path: `${shots}/kab-sbor-vozvrat.png`, fullPage: true })
  await l.getByRole('button', { name: 'Проверить и сдать →' }).click()
  await l.getByText('Оборудование: всё вернули').waitFor()
  await l.screenshot({ path: `${shots}/kab-sbor-itog.png`, fullPage: true })
  await l.getByRole('button', { name: 'Сдать проект' }).click()
  await l.getByText('Проект сдан.').waitFor()
  await l.getByText('RAL 3020 — 4').waitFor()
  await l.getByText('Фасадная: 10 л').waitFor()
  await l.screenshot({ path: `${shots}/kab-sbor-sdan.png` })

  // 3. Про выше Главного: видит и принимает смену Главного; Главный смену Про не видит
  const sh = await call(3000, '/shifts', { client_uid: crypto.randomUUID(), object_id: obj.id, zone_code: 'mural',
    started_at: '2026-11-04T09:00:00+05:00', ended_at: '2026-11-04T19:00:00+05:00' })
  const shp = await call(4000, '/shifts', { client_uid: crypto.randomUUID(), object_id: obj.id, zone_code: 'mural',
    started_at: '2026-11-04T09:00:00+05:00', ended_at: '2026-11-04T19:00:00+05:00' })
  assert.ok(!(await call(3000, '/review')).shifts.some(x => x.id === shp.id))
  const pr = await open(b, 4000)
  await tab(pr, 'Проверка')
  await pr.getByText('Главный Ержан').first().waitFor()
  await pr.getByRole('button', { name: '✓' }).first().click()
  await pr.waitForTimeout(500)
  assert.strictEqual((await call(3000, '/my')).shifts.find(x => x.id === sh.id).status, 'approved')

  // 4. Главный дизайнер: воронка «Дизайн РК», назначает помощника и размер XS, срок; запись в Битрикс
  const dz = await open(b, 7000)
  assert.deepStrictEqual(await navText(dz), ['Дизайн', 'Проекты', 'Проверка', 'Учёба', 'Кабинет', 'Расход'])
  await dz.locator('.dzfire .dzcard', { hasText: 'Дизайн кафе' }).getByText('нет дизайнера').waitFor()   // «Горит»: нет дизайнера и размера
  await dz.locator('.dzguide').first().getByText('Что делать').waitFor()
  await dz.screenshot({ path: `${shots}/kab-dizain.png`, fullPage: true })
  await dz.locator('.dzstage .dzcard', { hasText: 'Дизайн кафе' }).click()
  await dz.locator('.modal select').nth(1).selectOption({ label: 'Помощник Мира' })
  await dz.locator('.modal .chips button', { hasText: 'XS' }).click()
  await dz.locator('.modal input[type=date]').fill('2026-11-12')
  await dz.screenshot({ path: `${shots}/kab-dizain-karta.png` })
  await dz.getByRole('button', { name: 'Сохранить в Битрикс' }).click()
  await dz.locator('.modal').waitFor({ state: 'detached' })
  await dz.locator('.dzstage .dzcard').getByText(/Помощник Мира · XS · 0,5 ед./).waitFor()
  const calls = await (await fetch(API + '/_e2e/bx_calls')).json()
  const upd = calls.filter(c => c.method === 'crm.deal.update' && c.params.id === 1647).pop()
  assert.strictEqual(upd.params.fields.UF_CRM_ARTGAME_DESIGNER, 4693)
  assert.ok(!('UF_CRM_ARTGAME_DESIGN_COMPLEXITY' in upd.params.fields), 'XS в Битриксе нет — хранится в приложении')

  // 5. Помощник: видит свою сделку, отправляет каталог референсов вдвоём; HEAD утверждает
  const as = await open(b, 7100)
  await as.locator('.dzstage .dzcard', { hasText: 'Дизайн кафе' }).waitFor()
  await as.getByRole('button', { name: 'Каталоги' }).click()
  await as.getByRole('button', { name: '+ Новый' }).click()
  await as.getByPlaceholder('Название').fill('Лофт')
  await as.getByPlaceholder('Ссылка на папку или рефборд').fill('https://drive.google.com/x')
  await as.locator('.warnbox .chips button', { hasText: 'Главный дизайнер Алия' }).click()
  await as.getByRole('button', { name: 'Сохранить' }).click()
  await as.getByText('Лофт').waitFor()
  await as.getByRole('button', { name: 'Отправить HEAD' }).click()
  await as.getByText('у HEAD').waitFor()
  await as.screenshot({ path: `${shots}/kab-katalog.png` })
  const h = await open(b, 1000)
  await tab(h, 'Дизайн')
  await h.getByRole('button', { name: 'Каталоги' }).click()
  await h.getByRole('button', { name: 'Утверждаю' }).click()
  await h.getByText('утверждено').waitFor()
  const cat = (await call(7100, '/design/catalogs')).rows[0]
  assert.strictEqual(cat.status, 'approved')
  assert.deepStrictEqual(cat.authors.sort(), [ids[7000], ids[7100]].sort())
  // 6. И.о. (HEAD 09.11): художник исполняет обязанности Главного — меню Главного, ставка художника, повышение 15.12
  await call(1000, `/people/${ids[2000]}`, { acting_role: 'lead_artist', acting_promo: '2026-12-15', acting_note: 'День рождения команды!' })
  const io = await open(b, 2000)
  assert.deepStrictEqual(await navText(io), ['Сбор', 'Смена', 'Расход', 'Продакшн', 'Проверка', 'Проекты', 'Учёба', 'Кабинет'])
  await tab(io, 'Кабинет')
  await io.getByText('Ты — и.о. Главного художника').waitFor()
  await io.getByText('Повышение — 15 декабря.').waitFor()
  await io.getByText('Художник · и.о. Главного художника').waitFor()
  await io.getByText(/15\s000 ₸/).first().waitFor()   // ставка — художника
  await io.screenshot({ path: `${shots}/kab-io.png` })
  // «Как подняться»: у Главного — к Про, у художника — к Главному; самопроверка «есть / нет»
  await io.locator('.dutyfold').first().getByRole('button', { name: 'Открыть' }).click()
  await io.getByText('Как стать Художником-Про').waitFor()
  await io.locator('.grow .growrow').first().click()
  await io.getByText('есть 1 из 7').waitFor()
  await io.locator('.grow').scrollIntoViewIfNeeded()
  await io.screenshot({ path: `${shots}/kab-grow-pro.png` })
  // HEAD в «Команде»: поле и.о. и день повышения
  await tab(h, 'Команда')
  await h.getByText('Исполняет обязанности (и.о.)').first().waitFor()
  await h.locator('input[type=date]').first().waitFor()
  // 7. HEAD 09.11: «Оплачиваемые рилс» дизайнеру — появляется «Продакшн»
  await call(1000, `/people/${ids[7000]}`, { reels: true })
  const gl = await open(b, 7000)
  assert.ok((await navText(gl)).includes('Продакшн'))
  // 8. «Прошлая смена» с 1.11 (кнопка открыта до даты из настроек сервера)
  if ((await call(2000, '/work/dict')).backfill.open) {
    await tab(io, 'Смена')
    await io.locator('.card.past').getByRole('button', { name: 'Внести' }).click()
    const y = new Date(Date.now() - 864e5).toISOString().slice(0, 10)
    await io.locator('.card.past input[type=date]').fill(y)
    await io.locator('.card.past textarea').fill('Фон и контур')
    // сколько угодно фото из галереи (HEAD 09.11)
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEklEQVR4nGP4z8CAFWEXHbQSACj/P8Fu7N9hAAAAAElFTkSuQmCC', 'base64')
    await io.locator('.card.past .pics input[type=file]').setInputFiles([1, 2, 3].map(i => ({ name: `p${i}.png`, mimeType: 'image/png', buffer: png })))
    await io.getByText('Фото работы · выбрано 3').waitFor()
    await io.locator('.card.past').getByRole('button', { name: 'Отправить на проверку' }).click()
    await io.getByText(/ушла на проверку, фото: 3/).waitFor()
  }
  // 9. ГИП проекта: HEAD назначает в карточке проекта, ГИП видит всю историю
  execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1700, 'Школа', 'Шымкент', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING"`)
  await h.reload()
  await tab(h, 'Проекты')
  await h.locator('.pcard').first().click()
  await h.locator('.gippick select').selectOption({ label: 'Главный Ержан · Главный художник' })
  await h.getByText(/ГИП — Главный Ержан/).waitFor()
  await tab(l, 'Проекты')
  await l.reload(); await tab(l, 'Проекты')
  await l.locator('.pcard').first().click()
  await l.getByText('Ты ГИП · вся история проекта').waitFor()
  await l.screenshot({ path: `${shots}/gip-history.png`, fullPage: true })
  console.log('OK: меню по ролям, сбор на объект, Про проверяет Главного, воронка дизайна, каталог референсов, своя ставка, и.о. Главного, как подняться, рилс, прошлая смена, ГИП')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

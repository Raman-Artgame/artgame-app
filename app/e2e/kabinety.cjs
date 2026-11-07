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
  execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "INSERT INTO objects (id, title, city) VALUES (731, 'Кафе e2e', 'Астана') ON CONFLICT DO NOTHING"`)
  const obj = (await call(3000, '/work/dict')).objects.find(o => o.id)
  assert.ok(obj, 'нужен активный объект')

  // 1. Меню по ролям
  const a = await open(b, 2000)
  assert.deepStrictEqual(await navText(a), ['Смена', 'Расход', 'Проекты', 'Учёба', 'Мои', 'Объекты'])
  await tab(a, 'Расход')
  await a.getByRole('button', { name: 'Закупка на склад' }).click()
  await a.getByRole('button', { name: '+ Покупка' }).waitFor()
  await tab(a, 'Мои')
  await a.getByText('Моя ставка').waitFor()
  await a.getByText(/15\s000 ₸/).first().waitFor()
  await a.screenshot({ path: `${shots}/kab-artist-moi.png` })

  // 2. Главный художник: «Сбор на объект» — аэрозоль номер—штук, фасадная литры, оборудование, сдать проект
  const l = await open(b, 3000)
  assert.deepStrictEqual(await navText(l), ['Смена', 'Расход', 'Проверка', 'Учёба', 'Мои', 'Ещё'])
  await tab(l, 'Сбор')
  await l.getByText(obj.title).waitFor()
  await l.locator('.row', { hasText: obj.title }).getByRole('button', { name: /Роспись/ }).click()
  await l.getByRole('button', { name: '+ цвет' }).click()
  const ar = l.locator('.kitrow').first()
  await ar.locator('input').nth(0).fill('RAL 3020')
  await ar.locator('input').nth(1).fill('6')
  const fac = l.locator('.kitrow', { hasText: 'Всего' })
  await fac.locator('input').nth(0).fill('12,5')
  const obr = l.locator('.kitobr', { hasText: 'Стремянки' })
  await obr.locator('input[type=checkbox]').first().check()
  await obr.locator('select').first().selectOption('исправно')
  await l.getByRole('button', { name: 'Сохранить' }).click()
  await l.getByText('Сохранено.').waitFor()
  await l.screenshot({ path: `${shots}/kab-sbor.png`, fullPage: true })
  await l.getByRole('button', { name: 'Сдать проект' }).click()
  await l.getByText(/Не всё отмечено/).waitFor()
  await ar.locator('input').nth(2).fill('2')
  await fac.locator('input').nth(1).fill('2,5')
  await obr.getByText('вернул').click()
  await obr.locator('select').nth(1).selectOption('есть замечание')
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
  assert.deepStrictEqual(await navText(dz), ['Дизайн', 'Проекты', 'Проверка', 'Учёба', 'Мои', 'Расход'])
  await dz.getByText('Дизайн кафе').waitFor()
  await dz.screenshot({ path: `${shots}/kab-dizain.png` })
  await dz.getByText('Дизайн кафе').click()
  await dz.locator('.modal select').nth(1).selectOption({ label: 'Помощник Мира' })
  await dz.locator('.modal .chips button', { hasText: 'XS' }).click()
  await dz.locator('.modal input[type=date]').fill('2026-11-12')
  await dz.screenshot({ path: `${shots}/kab-dizain-karta.png` })
  await dz.getByRole('button', { name: 'Сохранить в Битрикс' }).click()
  await dz.locator('.modal').waitFor({ state: 'detached' })
  await dz.getByText(/Помощник Мира · XS · 0.5 ед./).waitFor()
  const calls = await (await fetch(API + '/_e2e/bx_calls')).json()
  const upd = calls.filter(c => c.method === 'crm.deal.update' && c.params.id === 1647).pop()
  assert.strictEqual(upd.params.fields.UF_CRM_ARTGAME_DESIGNER, 4693)
  assert.ok(!('UF_CRM_ARTGAME_DESIGN_COMPLEXITY' in upd.params.fields), 'XS в Битриксе нет — хранится в приложении')

  // 5. Помощник: видит свою сделку, отправляет каталог референсов вдвоём; HEAD утверждает
  const as = await open(b, 7100)
  await as.getByText('Дизайн кафе').waitFor()
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
  console.log('OK: меню по ролям, сбор на объект, Про проверяет Главного, воронка дизайна, каталог референсов, своя ставка')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

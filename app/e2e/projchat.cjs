// Чат проекта (HEAD 13.11): создаётся сам у проекта на «Выполнении»; кнопка «Чат проекта» в карточке, раздел «Проекты» в «Чате».
// Видят: кто на объекте, ГИП, МОП, все HEAD. Ширина iPhone 375. Скриншоты — в SHOTS.
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
const sql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "${q}"`)

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 375, height: 740 }, deviceScaleFactor: 2 })
  const pg = await ctx.newPage()
  const d = sign(id)
  await pg.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await pg.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await pg.goto('http://127.0.0.1:4173/')
  await pg.locator('nav').waitFor()
  return pg
}
const noScroll = async pg => assert.ok(await pg.evaluate(() => document.documentElement.scrollWidth <= 375), 'горизонтальная прокрутка')

;(async () => {
  await call(1000, '/register', { full_name: 'Раман Холопов' })
  const ids = {}
  for (const [tg, name, role, zones] of [[7801, 'Ангелина Ким', 'lead_artist', ['mural']], [7802, 'Данияр Сапаров', 'artist', ['mural']],
    [7804, 'Тимур Абенов', 'mop', []], [7805, 'Айгерим Нурлан', 'artist', ['mural']]]) {
    const p = await call(tg, '/register', { full_name: name })
    await call(1000, `/people/${p.id}`, { role_code: role, zones })
    ids[tg] = p.id
  }
  sql(`INSERT INTO objects (id, title, city, bitrix_stage, mop_bx_id) VALUES (1700, '1700 · ШКОЛА — ШЫМКЕНТ', 'ШЫМКЕНТ', 'UC_AV00QK', 4693) ON CONFLICT (id) DO UPDATE SET mop_bx_id=4693`)
  sql(`UPDATE people SET bitrix_user_id=4693 WHERE id=${ids[7804]}`)
  await call(1000, '/objects/1700/gip', { person_id: ids[7801] })
  await call(1000, '/objects/1700/crew', { person_id: ids[7802] })
  const b = await chromium.launch()

  // художник на объекте: «Проекты» → карточка → «Чат проекта» (создаваться не нужно — уже есть)
  const art = await open(b, 7802)
  await art.locator('nav button', { hasText: 'Проекты' }).click()
  await art.locator('.pcard').first().click()
  await art.locator('.pchatbtn').waitFor()
  await noScroll(art)
  await art.screenshot({ path: `${shots}/pchat-card.png` })
  await art.locator('.pchatbtn').click()
  await art.getByRole('heading', { name: 'Чат проекта' }).waitFor()
  await art.locator('.dm textarea').fill('Стена у входа сырая, грунт завтра после обеда. Краски хватит на 2 дня.')
  await art.getByRole('button', { name: 'Отправить' }).click()
  await art.locator('.dmb.me').waitFor()

  // МОП и ГИП отвечают через API, HEAD открывает «Чат» → «Проекты»
  await call(7804, '/pchat/1700', { text: 'Клиент просит закончить фасад к пятнице. Успеваем?' })
  await call(7801, '/pchat/1700', { text: 'Успеваем, завтра ставлю ещё Айгерим.' })
  const head = await open(b, 1000)
  await head.locator('nav button', { hasText: 'Ещё' }).click()
  await head.locator('button', { hasText: 'Чат' }).first().click()
  await head.locator('.dmproj').waitFor()
  assert.ok((await head.locator('.dmproj .dmcnt').innerText()) === '3')
  await noScroll(head)
  await head.screenshot({ path: `${shots}/pchat-head-list.png`, fullPage: true })
  await head.locator('.dmproj').click()
  await head.locator('.dmb').nth(2).waitFor()
  await head.getByRole('button', { name: /Участники: 4/ }).click()
  await noScroll(head)
  await head.screenshot({ path: `${shots}/pchat-head-room.png`, fullPage: true })

  // сотрудник не на объекте: кнопки нет, чат закрыт
  const other = await open(b, 7805)
  await other.locator('nav button', { hasText: 'Проекты' }).click()
  await other.locator('.pcard').first().click()
  await other.getByText('Открыть сделку').or(other.locator('.kvgrid')).first().waitFor()
  assert.strictEqual(await other.locator('.pchatbtn').count(), 0)
  assert.strictEqual((await call(7805, '/pchat/1700')).detail, 'чат проекта недоступен')
  await b.close()
  console.log('projchat ok')
})().catch(e => { console.error(e); process.exit(1) })

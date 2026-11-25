// Сквозной тест «Задачи на дизайн при сделке» (HEAD 25.11): МОП в карточке сделки жмёт «Нужен дизайн» — сделка стоит на месте,
// у дизайнера во вкладке «Дизайн» карточка на доске; он берёт её, вставляет эскиз и утверждает; МОП видит «УТВЕРЖДЕНО».
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
const bxCalls = async () => (await fetch(API + '/_e2e/bx_calls')).json()
const shots = process.env.SHOTS || '/var/tmp'

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 800 } })
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
  const re = new RegExp(`^${name}\\s*\\d*$`)
  await nav.locator('button').first().waitFor()
  if (await nav.getByRole('button', { name: re }).waitFor({ timeout: 1500 }).then(() => true, () => false)) return nav.getByRole('button', { name: re }).click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const ids = {}
  for (const [tg, name, role, zones, bxu] of [[6000, 'Ануар', 'mop', ['sales'], 4565], [7100, 'Малика', 'designer_asst', ['design'], 4693]]) {
    ids[tg] = (await call(tg, '/register', { full_name: name })).id
    await call(1000, `/people/${ids[tg]}`, { role_code: role, zones, bitrix_user_id: bxu })
  }

  // 1. МОП: карточка сделки → «Нужен дизайн» дважды
  const m = await open(b, 6000)
  await tab(m, 'Сделки')
  await m.locator('.chips.scroll button', { hasText: 'Все' }).click()
  await m.locator('.stage .qrow', { hasText: '№ 1601' }).click()
  await m.locator('.dtdeal').waitFor()
  await m.waitForTimeout(800)
  const before = (await bxCalls()).length   // карточка при открытии сама дописывает своё — считаем после
  for (const [title, note] of [['Столовая', 'Стена 6×3 м у раздачи, детская тема'], ['Спортзал', 'Две стены, тема спорт']]) {
    await m.locator('.dtdeal').getByRole('button', { name: '+ Нужен дизайн' }).click()
    await m.locator('.sheetbox input').first().fill(title)
    await m.locator('.sheetbox textarea').fill(note)
    await m.locator('.sheetbox').getByRole('button', { name: 'Отправить дизайнеру' }).click()
    await m.locator('.dtdeal .dtrow', { hasText: title }).waitFor()
  }
  assert.strictEqual(await m.locator('.dtdeal .dtrow').count(), 2)
  assert.match(await m.locator('.dtdeal .dtrow').first().textContent(), /Столовая.*дизайнер не назначен.*Свежие заказы/)
  assert.strictEqual((await bxCalls()).length, before, 'в Битрикс ничего не пишем: сделка стоит на своей стадии')
  await m.locator('.dtdeal').scrollIntoViewIfNeeded()
  await m.screenshot({ path: `${shots}/dz-task-1-mop.png`, fullPage: true })

  // 2. Дизайнер: «Дизайн» сразу открывает доску задач
  const d = await open(b, 7100)
  await tab(d, 'Дизайн')
  await d.locator('.dtstage .dtrow', { hasText: 'Столовая' }).waitFor()
  assert.match(await d.locator('.segf button.on').first().textContent(), /Задачи2/)
  assert.match(await d.locator('.dtstage').first().textContent(), /Свежие заказы.*№ 1601.*Столовая/)
  await d.screenshot({ path: `${shots}/dz-task-2-board.png`, fullPage: true })

  // 3. Берёт задачу, без эскиза «Утверждено» не проходит, со ссылкой — проходит
  await d.locator('.dtstage .dtrow', { hasText: 'Столовая' }).click()
  await d.locator('.sheetbox').getByRole('button', { name: 'Беру в работу' }).click()
  await d.locator('.sheetbox select').first().waitFor()
  await d.waitForFunction(() => document.querySelector('.sheetbox select')?.value === 'work')
  await d.locator('.sheetbox select').nth(1).selectOption('l')
  await d.waitForFunction(() => document.querySelectorAll('.sheetbox select')[1]?.value === 'l')
  await d.locator('.sheetbox').getByRole('button', { name: 'Утверждено' }).click()
  await d.locator('.sheetbox .why', { hasText: 'Сначала загрузите эскиз' }).waitFor()
  await d.locator('.sheetbox input[placeholder="или ссылка на эскиз"]').fill('https://drive.google.com/file/d/e2e-stolovaya')
  await d.locator('.sheetbox h3').click()
  await d.waitForTimeout(500)
  await d.screenshot({ path: `${shots}/dz-task-3-card.png`, fullPage: true })
  await d.locator('.sheetbox').getByRole('button', { name: 'Утверждено' }).click()
  await d.locator('.dtstage.done .dtrow', { hasText: 'Столовая' }).waitFor()
  assert.match(await d.locator('.dtstage.work, .dtstage.new').first().textContent(), /Спортзал/)

  // 4. МОП видит результат в сделке; единиц задача не дала
  const t = (await call(6000, '/bx/deals/1601/design-tasks')).items
  assert.deepStrictEqual(t.map(x => [x.title, x.stage_name, x.designer]), [['Столовая', 'УТВЕРЖДЕНО', 'Малика'], ['Спортзал', 'Свежие заказы', '']])
  const u = await call(7100, `/design/units?ym=${new Date().toISOString().slice(0, 7)}`)
  assert.strictEqual(u.mine, 0, 'задачи единиц не дают: единица одна за весь проект')
  await b.close()
  console.log('OK: МОП просит дизайн из сделки, дизайнер ведёт задачу на доске и утверждает, сделка на месте, единиц нет')
})().catch(e => { console.error('FAIL', e.message); process.exit(1) })

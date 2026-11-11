// «Диалог с HEAD» (HEAD 09.11): сотрудник пишет во вкладке «HEAD», HEAD видит в «Пульте» и «Сообщениях», отвечает и пишет всем.
// Ширина iPhone 375: слова не рвутся, панель у нижнего края. Скриншоты — в SHOTS.
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
  const ctx = await b.newContext({ viewport: { width: 375, height: 740 }, deviceScaleFactor: 2 })
  const pg = await ctx.newPage()
  const d = sign(id)
  await pg.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await pg.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await pg.goto('http://127.0.0.1:4173/')
  await pg.locator('nav').waitFor()
  return pg
}

;(async () => {
  await call(1000, '/register', { full_name: 'Раман Холопов' })
  const people = [[7801, 'Ангелина Ким', 'lead_artist', ['mural']], [7802, 'Данияр Сапаров', 'artist', ['mural']], [7803, 'Малика Ахметова', 'lead_designer', ['design']],
    [7900, 'Алина Сергеева', 'head', []]]
  for (const [tg, name, role, zones] of people) {
    const p = await call(tg, '/register', { full_name: name })
    await call(1000, `/people/${p.id}`, { role_code: role, zones })
  }
  const b = await chromium.launch()
  // сотрудник: «Чат» → подгруппы; пишет лично Раману и в «Руководство»
  const art = await open(b, 7802)
  await art.locator('nav button', { hasText: 'Чат' }).click()
  await art.locator('.dmrow').nth(3).waitFor()
  assert.deepStrictEqual(await art.locator('.dmrow b').allTextContents(), ['Объявления', 'Руководство', 'Раман Холопов', 'Алина Сергеева'])
  await art.screenshot({ path: `${shots}/chat-worker-rooms.png` })
  await art.locator('.dmrow', { hasText: 'Раман Холопов' }).click()
  await art.getByText('Увидит только Раман Холопов').waitFor()
  await art.locator('.dm textarea').fill('Раман, можно завтра выйти на час позже? Личное.')
  await art.getByRole('button', { name: 'Отправить' }).click()
  await art.locator('.dmb.me').waitFor()
  await art.getByRole('button', { name: '‹ Все чаты' }).click()
  await art.locator('.dmrow', { hasText: 'Руководство' }).click()
  await art.getByText('Увидит всё руководство').waitFor()
  await art.locator('.dm textarea').fill('На объекте УЙДОМДОНЕР закончилась белая краска. Докупить самому?')
  await art.getByRole('button', { name: 'Отправить' }).click()
  await art.locator('.dmb.me').waitFor()
  await art.screenshot({ path: `${shots}/chat-worker-group.png` })
  // Алина (HEAD): «Руководство» видит, личного Раману — нет; отвечает
  const al = await open(b, 7900)
  await al.locator('nav button', { hasText: 'Ещё' }).click()
  await al.locator('.sheetbox button', { hasText: 'Чат' }).click()
  await al.locator('.dmrow', { hasText: 'Данияр Сапаров' }).waitFor()
  await al.screenshot({ path: `${shots}/chat-head2-group.png` })
  await al.locator('.dmseg button', { hasText: 'Личные' }).click()
  assert.equal(await al.getByText('можно завтра выйти').count(), 0, 'Алина не видит личное Раману')
  await al.locator('.dmseg button', { hasText: 'Руководство' }).click()
  await al.locator('.dmrow', { hasText: 'Данияр Сапаров' }).click()
  await al.locator('.dm textarea').fill('Да, купи и внеси чек в «Расход».')
  await al.getByRole('button', { name: 'Отправить' }).click()
  await al.locator('.dmb.me').waitFor()
  await al.screenshot({ path: `${shots}/chat-head2-reply.png` })
  // Раман: личное от Данияра и ответ Алины в «Руководстве»
  const head = await open(b, 1000)
  await head.getByText(/Чат: новых/).click()
  await head.locator('.dmseg button', { hasText: 'Личные' }).click()
  await head.locator('.dmrow', { hasText: 'Данияр Сапаров' }).first().waitFor()
  await head.screenshot({ path: `${shots}/chat-head-personal.png` })
  await head.locator('.dmrow', { hasText: 'Данияр Сапаров' }).first().click()
  await head.getByText('можно завтра выйти').waitFor()
  await head.locator('.dm textarea').fill('Можно, предупреди Главного.')
  await head.getByRole('button', { name: 'Отправить' }).click()
  await head.locator('.dmb.me').waitFor()
  await head.getByRole('button', { name: '‹ Все чаты' }).click()
  await head.locator('.dmseg button', { hasText: 'Руководство' }).click()
  await head.locator('.dmrow', { hasText: 'Данияр Сапаров' }).click()
  await head.getByText('Алина Сергеева · ').waitFor()
  await head.getByRole('button', { name: '‹ Все чаты' }).click()
  // объявление художникам
  await head.locator('.dmseg button', { hasText: 'Объявления' }).click()
  await head.getByRole('button', { name: '📣 Написать всем' }).click()
  await head.locator('.chips button', { hasText: 'Главный художник' }).click()
  await head.locator('.chips button', { hasText: /^Художник\d/ }).click()
  await head.locator('.dm textarea').fill('Завтра в 9:00 общий сбор на складе.')
  await head.screenshot({ path: `${shots}/chat-head-broadcast.png` })
  await head.getByRole('button', { name: 'Отправить' }).click()
  await head.getByText('Отправлено: 2 чел.').waitFor()
  // сотрудник: полоса, цифра, три чата с новым
  await art.reload(); await art.locator('nav').waitFor()
  await art.locator('nav button', { hasText: 'Смена' }).click()
  await art.locator('.dmbar').waitFor()
  assert.equal(await art.locator('nav button', { hasText: 'Чат' }).locator('.cnt').textContent(), '3')
  await art.locator('.dmbar').click()
  await art.locator('.dmrow .dmcnt').first().waitFor()
  await art.screenshot({ path: `${shots}/chat-worker-new.png` })
  for (const t of ['Объявления', 'Руководство', 'Раман Холопов']) {
    await art.locator('.dmrow', { hasText: t }).click(); await art.locator('.dmb').first().waitFor()
    if (t === 'Объявления') { assert.equal(await art.locator('.dm textarea').count(), 0); await art.screenshot({ path: `${shots}/chat-worker-news.png` }) }
    await art.getByRole('button', { name: '‹ Все чаты' }).click(); await art.locator('.dmrow').first().waitFor()
  }
  await art.waitForTimeout(300)
  assert.equal(await art.locator('nav button', { hasText: 'Чат' }).locator('.cnt').count(), 0)
  // Малике (дизайн) объявление художникам не пришло
  const dz = await open(b, 7803)
  assert.equal(await dz.locator('.dmbar').count(), 0)
  for (const pg of [art, head, dz, al]) {
    const nav = await pg.locator('nav').boundingBox()
    assert(Math.abs(nav.y + nav.height - 740) < 2, 'панель не у нижнего края')
  }
  await b.close()
  console.log('dm ok')
})().catch(e => { console.error(e); process.exit(1) })

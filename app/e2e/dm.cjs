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
  const people = [[7801, 'Ангелина Ким', 'lead_artist', ['mural']], [7802, 'Данияр Сапаров', 'artist', ['mural']], [7803, 'Малика Ахметова', 'lead_designer', ['design']]]
  for (const [tg, name, role, zones] of people) {
    const p = await call(tg, '/register', { full_name: name })
    await call(1000, `/people/${p.id}`, { role_code: role, zones })
  }
  const b = await chromium.launch()
  // сотрудник: вкладка «HEAD», пишет
  const art = await open(b, 7802)
  await art.locator('nav button', { hasText: 'HEAD' }).click()
  await art.getByText('Сообщений пока нет.').waitFor()
  await art.locator('.dm textarea').fill('Раман, на объекте УЙДОМДОНЕР закончилась белая краска. Докупить самому или ждать доставку?')
  await art.getByRole('button', { name: 'Отправить' }).click()
  await art.locator('.dmb.me').waitFor()
  // HEAD: Пульт — счётчик, «Сообщения» из «Ещё», ответ
  const head = await open(b, 1000)
  await head.getByText('Сообщения от команды: 1').waitFor()
  await head.screenshot({ path: `${shots}/dm-head-pulse.png` })
  await head.getByText('Сообщения от команды: 1').click()
  await head.getByText('Данияр Сапаров').waitFor()
  await head.screenshot({ path: `${shots}/dm-head-list.png` })
  await head.getByText('Данияр Сапаров').click()
  await head.locator('.dm textarea').fill('Докупи сам, чек — в «Расход» на объект.')
  await head.getByRole('button', { name: 'Отправить' }).click()
  await head.locator('.dmb.me').waitFor()
  await head.screenshot({ path: `${shots}/dm-head-dialog.png` })
  // HEAD: написать всем художникам
  await head.getByRole('button', { name: '‹ Все диалоги' }).click()
  await head.getByRole('button', { name: '📣 Написать всем' }).click()
  await head.locator('.chips button', { hasText: 'Главный художник' }).click()
  await head.locator('.chips button', { hasText: /^Художник\d/ }).click()
  await head.locator('.dm textarea').fill('Завтра в 9:00 общий сбор на складе. Взять спецодежду.')
  await head.screenshot({ path: `${shots}/dm-head-broadcast.png` })
  await head.getByRole('button', { name: 'Отправить' }).click()
  await head.getByText('Отправлено: 2 чел.').waitFor()
  // сотрудник: полоса «Новое сообщение», цифра на вкладке, оба сообщения в диалоге
  await art.locator('nav button', { hasText: 'Смена' }).click()
  await art.reload(); await art.locator('nav').waitFor()
  await art.locator('.dmbar').waitFor()
  assert.equal((await art.locator('nav button', { hasText: 'HEAD' }).locator('.cnt').textContent()), '2')
  await art.screenshot({ path: `${shots}/dm-artist-bar.png` })
  await art.locator('.dmbar').click()
  await art.locator('.dmb.them').nth(1).waitFor()
  assert.equal(await art.locator('.dmcast').count(), 1)
  await art.screenshot({ path: `${shots}/dm-artist-dialog.png`, fullPage: true })
  assert.equal(await art.locator('.dmbar').count(), 0)
  assert.equal(await art.locator('nav button', { hasText: 'HEAD' }).locator('.cnt').count(), 0)   // прочитал — цифра ушла
  // Малике (дизайн) рассылка художникам не пришла
  const dz = await open(b, 7803)
  assert.equal(await dz.locator('.dmbar').count(), 0)
  for (const pg of [art, head, dz]) {
    const nav = await pg.locator('nav').boundingBox()
    assert(Math.abs(nav.y + nav.height - 740) < 2, 'панель не у нижнего края')
  }
  await b.close()
  console.log('dm ok')
})().catch(e => { console.error(e); process.exit(1) })

// Отчёт таргетолога (HEAD 26.11): таргетолог грузит файл отчёта, HEAD видит сверку с Meta и Битриксом, «Вернуть с вопросом» → ответ → «Принято».
// Рабочее место маркетинга (HEAD 14.11): Маркетолог ставит публикацию в контент-план с материалом из «Медиа»,
// отправляет HEAD; HEAD видит её на Пульте и в «Маркетинг → На утверждение», утверждает; маркетолог отмечает «Вышло» со ссылкой.
// Без «Утверждаю» кнопки «Вышло» нет. Скриншоты — ширина iPhone (390). API — e2e/fake_api.py.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const fs = require('fs')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const shots = process.env.SHOTS || '/var/tmp'
const IMG = process.env.IMG || '/mnt/project-files/design-kit/client-docs/assets'
const psql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "${q}"`)
const shot = async (p, n) => { await p.waitForTimeout(450); return p.screenshot({ path: `${shots}/${n}.png`, fullPage: !n.match(/new|pick|sent|review/) }) }   // лист снизу — по экрану, после анимации

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.goto('http://127.0.0.1:4173/')
  await p.locator('nav').waitFor()
  return p
}
async function tab(p, name) {
  const nav = p.locator('nav')
  const btn = nav.getByRole('button', { name, exact: true })
  if (await btn.waitFor({ timeout: 2000 }).then(() => true, () => false)) return btn.click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}
const noScroll = async p => assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'горизонтальная прокрутка')


;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'Раман Холопов' })
  const tid = (await call(2300, '/register', { full_name: 'Данияр Таргет' })).id
  await call(1000, `/people/${tid}`, { role_code: 'marketer', zones: ['marketing'], mkt_job: 'target' })
  const rows = [['a1', 'Макет 1 · артгейм гот. команда', 358.03, 64], ['a3', 'Макет 3 · горизонт кадры', 337.70, 60], ['a2', 'Макет 2 · худ. говорящая голова', 38.38, 6],
    ['k4', 'Картины 4 · говорящая голова', 72.20, 23]]
  for (const [id, n, sp, m] of rows) psql(`INSERT INTO mkt_meta_ad_day (ad_id, day, account, ad_name, campaign_id, campaign_name, spend, currency, impressions, clicks, messages) VALUES ('${id}', '2026-11-12', 'act_1', '${n}', 'c1', 'РК', ${sp}, 'USD', 40000, 150, ${m})`)
  // 1. Таргетолог: вкладка «Отчёты таргета», загрузка файла, период, итог и вывод
  const t = await open(b, 2300)
  await t.route('https://upload.example/**', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'drvBIG00000777' }) }))
  await tab(t, 'Маркетинг')
  await t.locator('.mktnav').getByRole('button', { name: 'Отчёты таргета' }).click()
  await t.getByText('Отчётов пока нет.').waitFor()
  await t.getByRole('button', { name: '+ Загрузить отчёт' }).click()
  await t.locator('.adrepform input[type=file]').setInputFiles({ name: 'Otchet RK 22.10-25.11.xlsx', mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', buffer: Buffer.from('XLSX-DATA') })
  await t.locator('.adrepfile', { hasText: 'Otchet RK' }).waitFor()
  await t.getByLabel('С', { exact: true }).fill('2026-10-22'); await t.getByLabel('По', { exact: true }).fill('2026-11-25')
  await t.getByPlaceholder('Кампании').fill('РК «Артгейм», РК «Картины»')
  await t.getByPlaceholder('Потрачено, $').fill('806,31'); await t.getByPlaceholder('Переписок').fill('153')
  await t.getByPlaceholder('Вывод').fill('Лучше всего Макет 1 и Макет 3. Макет 2 отключаем.')
  await noScroll(t); await shot(t, 'adrep-1-new')
  await t.getByRole('button', { name: 'Отправить HEAD' }).click()
  await t.locator('.adrep .badge', { hasText: 'у HEAD' }).waitFor()
  // 2. HEAD: строка на Пульте → отчёт со сверкой → «Вернуть с вопросом»
  const h = await open(b, 1000)
  await h.getByText('Отчёты таргетолога: 1').click()
  await h.locator('.adrep').getByText('Сверка: отчёт · Meta · Битрикс').waitFor()
  await h.locator('.adrepcols').getByText('· сходится').waitFor()
  await h.locator('.adrep .warnbox').getByText('Вывод').waitFor()
  await noScroll(h); await shot(h, 'adrep-2-head')
  await h.getByRole('button', { name: 'Вернуть с вопросом' }).click()
  await h.getByPlaceholder('Вопрос агентству').fill('Почему Макет 2 работал весь период?')
  await h.getByRole('button', { name: 'Отправить вопрос' }).click()
  await h.locator('.adrep .badge', { hasText: 'вернул с вопросом' }).waitFor()
  // 3. Таргетолог отвечает и отправляет снова → HEAD «Принято»
  await t.reload(); await t.locator('nav').waitFor()
  await tab(t, 'Маркетинг'); await t.locator('.mktnav').getByRole('button', { name: 'Отчёты таргета' }).click()
  await t.getByText('HEAD: Почему Макет 2 работал весь период?').first().waitFor()
  await t.getByRole('button', { name: 'Ответить и отправить снова' }).click()
  await t.getByPlaceholder('Вывод').fill('Макет 2 отключили 20.11, дальше только 1 и 3.')
  await t.getByRole('button', { name: 'Отправить HEAD' }).click()
  await t.locator('.adrep .badge', { hasText: 'у HEAD' }).waitFor()
  await h.reload(); await h.locator('nav').waitFor()
  await tab(h, 'Маркетинг'); await h.locator('.mktnav').getByRole('button', { name: 'Отчёты таргета' }).click()
  await h.getByRole('button', { name: 'Принято' }).click()
  await h.locator('.adrep .badge', { hasText: 'принято' }).waitFor()
  await shot(h, 'adrep-3-accepted')
  console.log('adreports ok')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

// Сквозной тест «Смены и расходы»: API на тестовой базе + vite preview.
// Запуск: см. app/README.md (API — e2e/fake_api.py, Диск подменён). Подпись Telegram делается тестовым токеном 123:test-token.
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

async function page(b, id, name) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 780 } })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(([d, name]) => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: name } }, ready() {} } } }, [d, name])
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  p.on('dialog', dl => dl.accept('Нет чека'))
  await p.goto('http://127.0.0.1:4173/')
  return { p, ctx }
}

async function tab(p, name) {
  const nav = p.locator('nav')
  const btn = nav.getByRole('button', { name, exact: true })
  if (await btn.waitFor({ timeout: 3000 }).then(() => true, () => false)) return nav.getByRole('button', { name, exact: true }).click()
  await nav.locator('button').last().click()   // «Ещё»
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const lead = await call(3000, '/register', { full_name: 'Главный' })
  await call(1000, `/people/${lead.id}`, { role_code: 'lead_artist', zones: ['mural'] })

  // 1. Художник регистрируется сам и ждёт роли
  const { p: a, ctx } = await page(b, 2000, 'Дана')
  // первый вход — анкета «Мои данные» (HEAD 09.11)
  const an = a.locator('.card.profile')
  await an.getByRole('button', { name: 'Сохранить' }).waitFor()
  await an.locator('input').nth(0).fill('Ахметова'); await an.locator('input').nth(1).fill('Дана')
  await an.locator('input[type=date]').fill('2000-05-01')
  await an.locator('input[inputmode=tel]').first().fill('+7 701 000 00 01')
  await an.getByRole('button', { name: 'Астана' }).click()
  await a.screenshot({ path: `${shots}/00-registr.png` })
  await an.getByRole('button', { name: 'Сохранить' }).click()
  await a.getByText('Заявка у HEAD').waitFor()
  await a.screenshot({ path: `${shots}/00-zayavka.png` })
  // HEAD назначает роль и зону на вкладке «Команда»
  const { p: h } = await page(b, 1000, 'HEAD')
  await tab(h, 'Команда')
  const row = h.locator('.person', { hasText: 'Дана' })
  await row.getByText('ждёт роли').waitFor()
  await row.locator('select').selectOption('artist')
  // зона роли ставится сама (08.11): «Роспись» уже включена, кликать не нужно
  await h.waitForFunction(() => [...document.querySelectorAll('.person')].find(r => r.textContent.includes('Дана'))
    ?.querySelector('.zones button:not(.ghost)')?.textContent === 'Роспись')
  await h.screenshot({ path: `${shots}/0-komanda.png` })
  await a.reload()

  // 2. Смена по шагам (HEAD 08.11): объект в работе, условия заполнил МОП → фото «до» → «Начать» → м², «что сделал», фото «после»
  const psql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "${q}"`)
  psql("INSERT INTO objects (id, title, city, bitrix_stage, level, area_m2, address, geo, drive_folder) VALUES (731, 'Кафе e2e', 'Астана', 'UC_AV00QK', 'medium', 60, 'Мангилик Ел 1', '51.09;71.41', 'deal-731') ON CONFLICT (id) DO UPDATE SET bitrix_stage='UC_AV00QK', level='medium', geo='51.09;71.41', drive_folder='deal-731'")
  psql(`INSERT INTO deal_calc (deal_id, data) VALUES (731, '{\\"in\\": {\\"service\\": \\"mural\\", \\"level\\": \\"medium\\", \\"extras\\": [\\"height\\"], \\"surface\\": true}}') ON CONFLICT DO NOTHING`)
  await a.reload()
  await a.getByRole('button', { name: 'Начать смену' }).waitFor()
  await a.locator('.promo').getByText('Средний').waitFor()
  assert.ok(await a.getByRole('button', { name: 'Начать смену' }).isDisabled())   // без фото «до» не начать
  await a.locator('.snap input[type=file]').setInputFiles(__dirname + '/chek.png')
  await a.locator('.snap img').waitFor()
  await a.screenshot({ path: `${shots}/1-smena.png`, fullPage: true })
  await a.getByRole('button', { name: 'Начать смену' }).click()
  await a.getByText('Смена идёт').waitFor()
  await a.locator('input[inputmode=decimal]').fill('12,5')
  await a.locator('textarea').fill('Загрунтовал стену и перенёс эскиз')
  await a.locator('.snap input[type=file]').setInputFiles(__dirname + '/chek.png')
  await a.locator('.snap img').waitFor()
  await a.screenshot({ path: `${shots}/1-smena-idet.png`, fullPage: true })
  await a.getByRole('button', { name: 'Закончить и отправить на проверку' }).click()
  await a.getByText('Смена закончена').waitFor()

  // 3. Расход без сети → очередь → сеть вернулась → ушёл
  await a.getByRole('button', { name: 'Расход' }).click()
  await a.locator('input[inputmode=numeric]').fill('15000')
  await a.locator('.receipt input').first().setInputFiles(__dirname + '/chek.png')   // из галереи (HEAD 10.11)
  await a.locator('.receipt img').waitFor()
  await a.screenshot({ path: `${shots}/rashod-chek.png`, fullPage: true })
  await ctx.setOffline(true)
  await a.getByRole('button', { name: 'Отправить расход' }).click()
  await a.getByText('Сохранено на телефоне').waitFor()
  await ctx.setOffline(false)
  await a.evaluate(() => window.dispatchEvent(new Event('online')))
  await a.waitForTimeout(800)
  await tab(a, 'Кабинет')
  await a.screenshot({ path: `${shots}/2-moi.png` })
  await a.getByText(/15\s000 ₸/).waitFor()
  await a.screenshot({ path: `${shots}/2-moi.png` })

  // 4. Главный художник проверяет: смену принимает, расход отклоняет с причиной
  const { p: l } = await page(b, 3000, 'Главный')
  await tab(l, 'Проверка')
  await l.getByText('Дана').first().waitFor()
  await l.screenshot({ path: `${shots}/3-proverka.png` })
  await l.getByRole('button', { name: '✓' }).first().click()
  await l.waitForTimeout(400)
  await l.getByRole('button', { name: '✕' }).first().click()
  await l.getByText('Всё проверено').nth(1).waitFor()

  // 5. «Проекты» = бывшие «Объекты» (HEAD 08.11): карточка проекта, фото с объекта и файл дизайна (большой файл — прямо в Google, здесь подменён)
  await call(1000, `/people/${(await call(1000, '/people')).find(x => x.full_name === 'Дана Ахметова').id}`, { zones: ['mural', 'design'] })
  psql("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1700, 'ШКОЛА', 'Шымкент', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")
  await a.reload()
  await a.route('https://upload.example/**', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'drvBIG00000001' }) }))
  await tab(a, 'Проекты')
  await a.locator('.pcard', { hasText: 'Школа' }).waitFor()
  await a.screenshot({ path: `${shots}/4-proekty.png`, fullPage: true })
  await a.locator('.pcard', { hasText: 'Школа' }).click()
  await a.locator('.phero').waitFor()
  await a.locator('.segf').getByRole('button', { name: 'Эскизы' }).waitFor()
  await a.locator('label.photo input[type=file]').setInputFiles({ name: 'Эскиз.psd', mimeType: 'image/vnd.adobe.photoshop', buffer: Buffer.from('PSD-DATA') })
  await a.getByText('Эскиз.psd').waitFor()
  await a.locator('.segf').getByRole('button', { name: 'Фото' }).click()
  await a.locator('label.photo input[type=file]').setInputFiles([__dirname + '/chek.png', __dirname + '/chek.png'])
  await a.locator('.grid img').nth(1).waitFor()
  await a.screenshot({ path: `${shots}/5-kartochka-proekta.png`, fullPage: true })

  const my = await call(2000, '/my')
  assert.deepStrictEqual(my.shifts.map(s => s.status), ['approved'])
  assert.deepStrictEqual(my.expenses.map(e => [e.status, e.reason]), [['rejected', 'Нет чека']])
  assert.strictEqual(Number(my.shifts[0].area_m2), 12.5)
  assert.ok(my.shifts[0].photo_before && my.shifts[0].photo_after && my.shifts[0].work_done)
  assert.strictEqual(my.shifts[0].complexity, 'medium')   // из сделки, не с телефона
  assert.ok(my.shifts[0].at_height && my.shifts[0].hard_surface)
  assert.match(my.expenses[0].receipt_url, /^\/api\/files\/\d+\/content\?exp=/)
  console.log('E2E OK')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

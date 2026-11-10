// Сквозной тест «Кабинет HEAD» (08.11): Пульт с тем, что ждёт решения, и «смотреть как сотрудник» —
// баннер, меню чужой роли, запись закрыта, выход одним нажатием, вход/выход в журнале HEAD. API — e2e/fake_api.py.
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
  const btn = nav.locator('button', { hasText: new RegExp(`^${name}\\d*$`) })
  if (await btn.waitFor({ timeout: 2000 }).then(() => true, () => false)) return btn.click()
  await nav.locator('button').last().click()   // «Ещё»
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'Раман HEAD' })
  const dana = (await call(2000, '/register', { full_name: 'Дана Художник' })).id
  await call(1000, `/people/${dana}`, { role_code: 'artist', zones: ['mural'] })
  await call(2600, '/register', { full_name: 'Новенький' })
  execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "INSERT INTO objects (id, title, city, bitrix_stage) VALUES (731, 'Кафе e2e', 'Астана', 'UC_AV00QK') ON CONFLICT (id) DO UPDATE SET bitrix_stage='UC_AV00QK'"`)
  const now = Date.now()
  // «сегодня» в Пульте — по Алматы (UTC+5): смена не раньше полуночи Алматы, иначе вечером тест падал
  const almatyMidnight = Math.floor((now + 5 * 3600e3) / 864e5) * 864e5 - 5 * 3600e3
  const st = Math.max(now - 3 * 3600e3, almatyMidnight + 60e3), en = Math.max(st + 60e3, now - 600e3)
  await call(2000, '/shifts', { client_uid: crypto.randomUUID(), object_id: 731, zone_code: 'mural', started_at: new Date(st).toISOString(),
    ended_at: new Date(en).toISOString(), area_m2: 6, complexity: 'medium' })

  // 1. HEAD открывает приложение — сразу Пульт
  const h = await open(b, 1000)
  const nav = await navText(h)
  assert.deepStrictEqual(nav.slice(0, 5), ['Пульт', 'Проверка', 'Сделки', 'Проекты', 'Финансы'], nav.join(','))
  await h.getByText('Ждёт вашего решения').waitFor()
  await h.getByText('Смены на проверке: 1').waitFor()
  await h.getByText('Ждут роли: 1').waitFor()
  await h.locator('#pulse-today').getByText('Дана Художник').waitFor()
  // HEAD 10.11: плитки «Деньги» — ждут оплаты, упущено, долг, в работе; «как посчитано» раскрывает прибыль
  const money = h.locator('.pulse-money')
  await money.getByText('Ждут оплаты: саппорт').waitFor()
  await money.getByText('Упущенная выручка').waitFor()
  assert.strictEqual(await money.getByText('Ушло').count(), 0, '«Ушло» заменено на «Упущенная выручка»')
  await money.getByText('как посчитано ›').click()
  await money.locator('.profitwhy').getByText('Выручка без НДС').waitFor()
  await money.scrollIntoViewIfNeeded()
  await money.screenshot({ path: `${shots}/pult-dengi.png` })
  await money.getByText('скрыть').click()
  assert.strictEqual(await h.locator('.viewas-card').count(), 0, 'на Пульте нет дублей: «Смотреть как» — отдельной кнопкой (HEAD 09.11)')
  assert.deepStrictEqual((await navText(h)), ['Пульт', 'Проверка', 'Сделки', 'Проекты', 'Финансы', 'Ещё'], 'у HEAD внизу главное, остальное в «Ещё»')
  await h.locator('nav button').last().click()
  assert.deepStrictEqual((await h.locator('.sheetbox button').allTextContents()).map(t => t.replace(/\d+$/, '')), ['Сообщения', 'Команда', 'Продакшн', 'Дизайн', 'Лиды', 'Учёба', 'Журнал'], 'в «Ещё» без Места, Месяца и «Смотреть как» (HEAD 09.11)')
  await h.mouse.click(5, 5)
  await h.screenshot({ path: `${shots}/pult.png`, fullPage: true })

  // 2. «Смотреть как» Дана из «Команды»: баннер, меню художника, разделов HEAD нет
  await tab(h, 'Команда')
  await h.getByText('смотреть как Дана').click()
  await h.locator('.viewas-bar').getByText('Дана Художник').waitFor()
  await h.locator('.viewas-bar').getByText('только просмотр').waitFor()
  const anav = await navText(h)
  assert.ok(anav.includes('Смена') && !anav.includes('Пульт') && !anav.includes('Финансы'), anav.join(','))
  await h.screenshot({ path: `${shots}/pult-viewas.png` })
  // 3. запись закрыта: смена не уходит ни сейчас, ни потом из очереди
  await h.locator('.snap input[type=file]').setInputFiles(__dirname + '/chek.png')
  await h.getByRole('button', { name: 'Начать смену' }).click()
  await h.locator('.viewas-bar').getByText(/Режим просмотра/).waitFor()
  const q = await h.evaluate(() => localStorage.getItem('artgame.queue.v1'))
  assert.ok(!q || q === '[]', 'в очередь ничего не легло: ' + q)
  assert.strictEqual((await call(2000, '/my')).shifts.length, 1)
  // 4. выход одним нажатием — снова Пульт HEAD
  await h.getByRole('button', { name: 'Вернуться к себе' }).click()
  await h.getByText('Ждёт вашего решения').waitFor()
  assert.strictEqual(await h.locator('.viewas-bar').count(), 0)

  // 5. роль целиком (человека ещё нет): МОП
  await tab(h, 'Команда'); await h.getByText('Посмотреть приложение глазами роли').click()
  await h.locator('.viewas-card > .chips').getByRole('button', { name: 'МОП', exact: true }).click()
  await h.locator('.viewas-bar').getByText('Пример: МОП').waitFor()
  assert.ok((await navText(h)).includes('Сегодня'))
  await h.getByRole('button', { name: 'Вернуться к себе' }).click()
  await h.getByText('Ждёт вашего решения').waitFor()

  // 6. журнал HEAD: вход и выход записаны, в журнале Даны чужих действий нет
  const j = await call(1000, '/journal')
  const acts = j.items.map(i => i.action)
  assert.strictEqual(acts.filter(a => a === 'view_as_start').length, 2)
  assert.strictEqual(acts.filter(a => a === 'view_as_stop').length, 2)
  const jd = await call(1000, `/journal?person=${dana}`)
  assert.ok(jd.items.every(i => !i.data?.view_as), 'в журнале Даны нет просмотра HEAD')
  await tab(h, 'Журнал')
  await h.getByText('Смотрел приложение как Дана Художник').waitFor()

  // 7. «Пройти как сотрудник · тест»: HEAD работает как «Тест · Саппорт» — смена уходит по-настоящему на проверку
  await tab(h, 'Команда'); await h.getByText('Посмотреть приложение глазами роли').click()
  // HEAD открыл саппорта «просмотром»: в «Смене» видно, что это просмотр, и есть кнопка перейти в тест
  await h.locator('.viewas-card > .chips').getByRole('button', { name: 'Саппорт', exact: true }).click()
  await h.locator('.viewas-bar').getByText('Пример: Саппорт').waitFor()
  await h.getByText('это только просмотр, смена не начнётся').waitFor()
  await h.getByRole('button', { name: 'Пройти как сотрудник · тест' }).click()
  await h.locator('.viewas-bar').getByText('Тест · Саппорт').waitFor()
  await h.locator('.viewas-bar').getByText('всё сохраняется по-настоящему').waitFor()
  await h.locator('.snap input[type=file]').setInputFiles(__dirname + '/chek.png')
  await h.locator('.snap img').waitFor()
  await h.getByRole('button', { name: 'Начать смену' }).click()
  await h.getByText('Смена идёт').waitFor()
  await h.locator('input[inputmode=decimal]').fill('3')
  await h.locator('textarea').fill('Тест HEAD: грунт')
  await h.locator('.snap input[type=file]').setInputFiles(__dirname + '/chek.png')
  await h.locator('.snap img').waitFor()
  await h.screenshot({ path: `${shots}/test-kak-saport.png`, fullPage: true })
  await h.getByRole('button', { name: 'Закончить и отправить на проверку' }).click()
  await h.getByText('Смена закончена').waitFor()
  await h.getByRole('button', { name: 'Вернуться к себе' }).click()
  await h.getByText('Ждёт вашего решения').waitFor()
  const rv = await call(1000, '/review')
  assert.ok(rv.shifts.some(x => x.person_name === 'Тест · Саппорт' && x.work_done === 'Тест HEAD: грунт'), JSON.stringify(rv.shifts.map(x => x.person_name)))
  console.log('OK: Пульт HEAD, смотреть как сотрудник и роль, только просмотр, выход, журнал, тест от лица саппорта')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

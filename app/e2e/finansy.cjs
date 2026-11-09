// Сквозной тест «Финансы» (HEAD 06.11): мастер-плотник вносит закупку в мастерскую холстов, HEAD видит её в «Закупках»,
// вносит остаток на начало, пересчитывает ФОТ, отмечает выплату; сотрудник видит «Мои выплаты». API — e2e/fake_api.py на пустой базе.
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
const PNG = 'data:image/png;base64,' + require('fs').readFileSync(__dirname + '/chek.png').toString('base64')

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 800 } })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  p.on('dialog', dl => dl.accept())
  await p.goto('http://127.0.0.1:4173/')
  return p
}
async function tab(p, name) {
  const nav = p.locator('nav')
  await nav.locator('button').first().waitFor()
  if (await nav.getByRole('button', { name, exact: true }).count()) return nav.getByRole('button', { name, exact: true }).click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  await call(1000, '/_e2e/consts', { 'stock.price_tolerance_pct': 15, 'fin.tax.ipn': 10, vat: 16 })
  const c = await call(4000, '/register', { full_name: 'Плотник Арман' })
  await call(1000, `/people/${c.id}`, { role_code: 'carpenter', zones: [] })
  const mo = await call(6000, '/register', { full_name: 'Мастер печати Дана' })
  await call(1000, `/people/${mo.id}`, { role_code: 'print_master', zones: ['print'] })

  // 1. Мастер-плотник: «Склад» открывается сразу на «Мастерской», рейка 50 м за 12 000 (240 ₸/м: выше ориентира 230, в потолке) — принято само
  const w = await open(b, 4000)
  await w.getByRole('button', { name: '+ Покупка' }).click()
  await w.getByPlaceholder('Найти позицию').fill('Рейка 2 × 4')
  await w.locator('button.catitem', { hasText: 'Рейка 2 × 4' }).first().click()
  await w.getByLabel('Количество').fill('50')
  await w.getByLabel('Сумма').fill('12000')
  await w.getByText('240 ₸ за ед. — выше ориентира').waitFor()
  await w.locator('label.photo input').setInputFiles(__dirname + '/chek.png')
  await w.getByText('Все цены в пределах потолка').waitFor()
  await w.screenshot({ path: `${shots}/sklad-form.png`, fullPage: true })
  await w.getByRole('button', { name: 'Записать покупку' }).click()
  await w.getByText('Покупка записана.').waitFor()
  await w.locator('.row', { hasText: 'Мастерская холстов' }).getByText('принято').waitFor()
  await w.screenshot({ path: `${shots}/fin-carpenter.png` })

  // 1б. Мастер печати (склад — только у Главных, Про и Мастера печати, HEAD 08.11): хозтовары, своя позиция без ориентира — уходит HEAD
  const mp = await open(b, 6000)
  await tab(mp, 'Расход')                     // склад — внутри «Расхода» (HEAD 08.11)
  await mp.getByRole('button', { name: 'Закупка на склад' }).click()
  await mp.getByRole('button', { name: '+ Покупка' }).click()
  await mp.locator('.chips button', { hasText: 'Хозтовары' }).click()
  await mp.getByPlaceholder('Найти позицию').fill('Чайник')
  await mp.getByRole('button', { name: /Нет в списке/ }).click()
  await mp.getByLabel('Сумма').fill('9000')
  await mp.locator('label.photo input').setInputFiles(__dirname + '/chek.png')
  await mp.getByText('уйдёт на одобрение HEAD').waitFor()
  await mp.getByRole('button', { name: 'Записать покупку' }).click()
  await mp.getByText('Покупка ушла на одобрение HEAD.').waitFor()


  // 2. HEAD: «Финансы» → «Закупки» видит закупку плотника
  const h = await open(b, 1000)
  await tab(h, 'Финансы')
  await h.getByText('Прибыль месяца').waitFor()
  await h.locator('.segf').getByRole('button', { name: 'Закупки' }).click()
  await h.locator('.row', { hasText: 'Плотник Арман' }).waitFor()
  // каталог: HEAD ставит ориентир чайнику-позиции нет, правит ориентир рейки
  await h.locator('.segf').getByRole('button', { name: 'Каталог и цены' }).click()
  await h.locator('.chips button', { hasText: 'Мастерская холстов' }).click()
  await h.locator('.row', { hasText: 'Рейка 2 × 4' }).first().click()
  await h.getByPlaceholder('Ориентир за единицу, ₸').fill('250')
  await h.getByRole('button', { name: 'Сохранить' }).click()
  await h.locator('.row', { hasText: 'Рейка 2 × 4' }).first().getByText(/250/).waitFor()
  await h.screenshot({ path: `${shots}/sklad-catalog.png` })
  // «Проверка»: покупка МОП ждёт с причиной
  await tab(h, 'Проверка')
  await h.getByText(/Хозтовары и офис · нет ориентира цены/).waitFor()
  await h.screenshot({ path: `${shots}/sklad-review.png` })
  await tab(h, 'Финансы')
  await h.getByText('Прибыль месяца').waitFor()

  // 3. «Деньги»: остаток на начало по Kaspi
  await h.locator('.segf').getByRole('button', { name: 'Деньги' }).click()
  await h.getByRole('button', { name: '+ Операция' }).click()
  await h.locator('.dealedit select').first().selectOption('opening')
  await h.getByPlaceholder('Сумма, ₸').fill('1500000')
  await h.getByRole('button', { name: 'Записать', exact: true }).click()
  await h.locator('.row', { hasText: 'Остаток на начало' }).waitFor()

  // 4. «ФОТ»: пересчёт — у плотника возмещение 12 000 (свои деньги), выплата с Kaspi
  await h.locator('.segf').getByRole('button', { name: 'ФОТ' }).click()
  await h.getByRole('button', { name: 'Пересчитать' }).click()
  const row = h.locator('.row', { hasText: 'Плотник Арман' }).first()
  await row.getByText('осталось 12').waitFor()
  await row.locator('.head').click()
  await row.getByPlaceholder(/Выплата/).fill('12000')
  await row.getByRole('button', { name: 'Отметить выплату' }).click()
  await h.locator('.row', { hasText: 'Плотник Арман' }).first().getByText('выплачено').waitFor()
  await h.screenshot({ path: `${shots}/fin-payroll.png` })

  // 5. Сводка: Kaspi 1 500 000 → 1 488 000, мастерская холстов 12 000
  await h.locator('.segf').getByRole('button', { name: 'Сводка' }).click()
  await h.locator('.row', { hasText: 'Kaspi' }).getByText(/1\s488\s000/).waitFor()
  await h.locator('.row', { hasText: 'Мастерская холстов' }).getByText(/12\s000/).waitFor()
  await h.screenshot({ path: `${shots}/fin-summary.png`, fullPage: true })

  // 6. Плотник видит «Мои выплаты»: выплачено 12 000, чужих сумм нет
  await tab(w, 'Кабинет')
  await w.getByText('Мои выплаты').waitFor()
  await w.locator('.kv > div', { hasText: 'Выплачено' }).getByText(/12\s000/).waitFor()
  const my = await call(4000, '/fin/my')
  assert.equal(my.paid, 12000)
  const denied = await fetch(API + '/fin/summary', { headers: { 'X-Telegram-Init-Data': sign(4000) } })
  assert.equal(denied.status, 403)
  await b.close()
  console.log('finansy: ok')
})().catch(e => { console.error(e); process.exit(1) })

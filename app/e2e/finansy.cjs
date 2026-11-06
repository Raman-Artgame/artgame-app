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
  if (await nav.getByRole('button', { name, exact: true }).count()) return nav.getByRole('button', { name, exact: true }).click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  await call(1000, '/_e2e/consts', { 'fin.canvas.limit_month': 50000, 'fin.tax.ipn': 10, vat: 16 })
  const c = await call(4000, '/register', { full_name: 'Плотник Арман' })
  await call(1000, `/people/${c.id}`, { role_code: 'carpenter', zones: [] })

  // 1. Мастер-плотник: вкладка «Склад», закупка бруса в пределах лимита — принята сама
  const w = await open(b, 4000)
  await w.getByText('Мастерская холстов: лимит на месяц').waitFor()
  await w.getByRole('button', { name: '+ Закупка' }).click()
  await w.getByRole('button', { name: 'Брус и подрамники' }).click()
  await w.getByPlaceholder('Сумма, ₸').fill('12000')
  await w.getByPlaceholder('Что купил').fill('брус 40×40, 20 шт')
  await w.locator('label.photo input').setInputFiles(__dirname + '/chek.png')
  await w.getByText('В пределах лимита').waitFor()
  await w.getByRole('button', { name: 'Записать закупку' }).click()
  await w.getByText('Закупка записана.').waitFor()
  await w.locator('.row', { hasText: 'Брус и подрамники' }).getByText('принято').waitFor()
  await w.screenshot({ path: `${shots}/fin-carpenter.png` })

  // 2. HEAD: «Финансы» → «Закупки» видит закупку плотника
  const h = await open(b, 1000)
  await tab(h, 'Финансы')
  await h.getByText('Прибыль месяца').waitFor()
  await h.locator('.segf').getByRole('button', { name: 'Закупки' }).click()
  await h.locator('.row', { hasText: 'Плотник Арман' }).waitFor()

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
  await tab(w, 'Мои')
  await w.getByText('Мои выплаты').waitFor()
  await w.locator('.kv > div', { hasText: 'Выплачено' }).getByText(/12\s000/).waitFor()
  const my = await call(4000, '/fin/my')
  assert.equal(my.paid, 12000)
  const denied = await fetch(API + '/fin/summary', { headers: { 'X-Telegram-Init-Data': sign(4000) } })
  assert.equal(denied.status, 403)
  await b.close()
  console.log('finansy: ok')
})().catch(e => { console.error(e); process.exit(1) })

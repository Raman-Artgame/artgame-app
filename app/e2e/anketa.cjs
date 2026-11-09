// Сквозной тест анкеты «Мои данные» (HEAD 09.11): новый человек сам заполняет ФИО, дату рождения, телефон, город —
// имя в приложении из анкеты, не из Telegram; HEAD видит анкету в «Команде»; правка в «Кабинете».
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = (id, first = 'tgname') => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'${first}'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const shots = process.env.SHOTS || '/var/tmp'

async function page(b, id, first) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } })
  const p = await ctx.newPage()
  const d = sign(id, first)
  await p.addInitScript(([d, first]) => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: first } }, ready() {} } } }, [d, first])
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.goto('http://127.0.0.1:4173/')
  return p
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const p = await page(b, 8800, 'mlk_99')
  await p.getByText('Добро пожаловать').waitFor()
  const card = p.locator('.card.profile')
  assert.strictEqual(await card.getByRole('button', { name: 'Сохранить' }).isDisabled(), true)
  const inp = card.locator('input')
  await inp.nth(0).fill('Жұмаділдина'); await inp.nth(1).fill('Малика')
  await card.locator('input[type=date]').fill('1999-12-16')
  await card.locator('input[inputmode=tel]').first().fill('+7 777 987 70 99')
  await card.getByRole('button', { name: 'Астана' }).click()
  await card.getByRole('button', { name: 'M', exact: true }).click()
  await p.screenshot({ path: `${shots}/anketa.png`, fullPage: true })
  await card.getByRole('button', { name: 'Сохранить' }).click()
  await p.getByText('Малика Жұмаділдина').waitFor()          // имя из анкеты, не «mlk_99»
  await p.getByText(/Заявка у HEAD/).waitFor()
  const row = (await call(1000, '/people')).find(x => x.full_name === 'Малика Жұмаділдина')
  assert.ok(row && row.birth_date === '1999-12-16' && row.city === 'Астана' && row.clothes_size === 'M', JSON.stringify(row))
  console.log('OK: анкета при первом входе, имя из анкеты, HEAD видит данные')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

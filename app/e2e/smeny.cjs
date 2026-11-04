// Сквозной тест «Смены и расходы»: API на тестовой базе + vite preview.
// Запуск: см. app/README.md (API — e2e/fake_api.py, Диск подменён). Подпись Telegram делается тестовым токеном 123:test-token.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = __dirname + '/../backend'
const sign = id => execSync(`cd ${BE} && .venv/bin/python -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
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

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const lead = await call(3000, '/register', { full_name: 'Главный' })
  await call(1000, `/people/${lead.id}`, { role_code: 'lead_artist', zones: ['mural'] })

  // 1. Художник регистрируется сам и ждёт роли
  const { p: a, ctx } = await page(b, 2000, 'Дана')
  await a.getByRole('button', { name: 'Отправить' }).click()
  await a.getByText('Заявка у HEAD').waitFor()
  const people = await call(1000, '/people')
  const art = people.find(x => x.full_name === 'Дана')
  await call(1000, `/people/${art.id}`, { role_code: 'artist', zones: ['mural'] })
  await a.reload()

  // 2. Смена онлайн
  await a.getByRole('button', { name: 'Отправить смену' }).waitFor()
  await a.locator('input[inputmode=decimal]').fill('12,5')
  await a.screenshot({ path: `${shots}/1-smena.png` })
  await a.getByRole('button', { name: 'Отправить смену' }).click()
  await a.getByText('Смена отправлена на проверку').waitFor()

  // 3. Расход без сети → очередь → сеть вернулась → ушёл
  await a.getByRole('button', { name: 'Расход' }).click()
  await a.locator('input[inputmode=numeric]').fill('15000')
  await a.locator('input[type=file]').setInputFiles(__dirname + '/chek.png')
  await a.locator('.photo img').waitFor()
  await ctx.setOffline(true)
  await a.getByRole('button', { name: 'Отправить расход' }).click()
  await a.getByText('Сохранено на телефоне').waitFor()
  await ctx.setOffline(false)
  await a.evaluate(() => window.dispatchEvent(new Event('online')))
  await a.waitForTimeout(800)
  await a.getByRole('button', { name: 'Мои' }).click()
  await a.screenshot({ path: `${shots}/2-moi.png` })
  await a.getByText(/15\s000 ₸/).waitFor()
  await a.screenshot({ path: `${shots}/2-moi.png` })

  // 4. Главный художник проверяет: смену принимает, расход отклоняет с причиной
  const { p: l } = await page(b, 3000, 'Главный')
  await l.getByRole('button', { name: 'Проверка' }).click()
  await l.getByText('Дана').first().waitFor()
  await l.screenshot({ path: `${shots}/3-proverka.png` })
  await l.getByRole('button', { name: '✓' }).first().click()
  await l.waitForTimeout(400)
  await l.getByRole('button', { name: '✕' }).first().click()
  await l.getByText('Всё проверено').nth(1).waitFor()

  const my = await call(2000, '/my')
  assert.deepStrictEqual(my.shifts.map(s => s.status), ['approved'])
  assert.deepStrictEqual(my.expenses.map(e => [e.status, e.reason]), [['rejected', 'Нет чека']])
  assert.strictEqual(Number(my.shifts[0].area_m2), 12.5)
  assert.match(my.expenses[0].receipt_url, /^https:\/\/drive\.example\/0\//)
  console.log('E2E OK')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

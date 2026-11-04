// Скрины смены по роли (для HEAD): роспись с условиями и печать с бонусом.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const BE = __dirname + '/../backend'
const sign = id => execSync(`cd ${BE} && .venv/bin/python -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const shots = process.env.SHOTS || '/var/tmp'
;(async () => {
  const pm = await call(2300, '/register', { full_name: 'Мастер печати' })
  await call(1000, `/people/${pm.id}`, { role_code: 'print_master', zones: ['print'] })
  const b = await chromium.launch()
  for (const [id, name, m2, act] of [[2100, 'mural', '9', async p => { await p.getByRole('button', { name: 'Сложный' }).click(); await p.getByText('На высоте').click() }],
    [2300, 'print', '29', async () => {}]]) {
    const ctx = await b.newContext({ viewport: { width: 390, height: 900 }, deviceScaleFactor: 2 })
    const p = await ctx.newPage()
    const d = sign(id)
    await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: {} }, ready() {} } } }, d)
    await p.goto('http://127.0.0.1:4173/')
    await p.getByRole('button', { name: 'Смена' }).click()
    await p.locator('input[inputmode=decimal]').fill(m2)
    await act(p)
    await p.screenshot({ path: `${shots}/shift-${name}.png`, fullPage: true })
    await p.getByRole('button', { name: 'Отправить смену' }).click()
    await p.waitForTimeout(1500)
    await p.screenshot({ path: `${shots}/shift-${name}-mine.png` })
  }
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

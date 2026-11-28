// Лиды канбаном (HEAD 28.11 «лиды так же нужно сделать эту историю канбаном»): на компьютере колонки по статусам Битрикса,
// карточку тянут мышью в другой статус (crm.lead.update); на телефоне — статусы кнопками и список во всю ширину.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const bxCalls = async () => (await fetch(API + '/_e2e/bx_calls')).json()
const shots = process.env.SHOTS || '/var/tmp'
const noScroll = async p => assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'нет прокрутки вбок')

async function open(b, id, width = 390, height = 844) {
  const ctx = await b.newContext({ viewport: { width, height }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.route('https://fonts.googleapis.com/**', r => r.fulfill({ body: '', contentType: 'text/css' }))
  await p.goto('http://127.0.0.1:4173/')
  return p
}
async function tab(p, name) {
  const nav = p.locator('nav')
  await nav.locator('button').first().waitFor()
  const re = new RegExp(`^${name}\\s*\\d*$`)
  if (await nav.getByRole('button', { name: re }).waitFor({ timeout: 1500 }).then(() => true, () => false)) return nav.getByRole('button', { name: re }).click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const m = await call(6100, '/register', { full_name: 'Ануар', phone: '+7 701 111 22 34' })
  await call(1000, `/people/${m.id}`, { role_code: 'mop', zones: ['sales'], bitrix_user_id: 4565 })

  // компьютер: колонки «Новый лид», «В работе»; вакансий и отказов нет
  const p = await open(b, 6100, 1440, 900)
  await tab(p, 'Лиды')
  const kb = p.locator('.kb.leadsb')
  await kb.waitFor()
  assert.deepStrictEqual(await kb.locator('.khead span').allTextContents(), ['Новый лид', 'В работе'], 'колонки — рабочие статусы по порядку')
  const col = n => kb.locator('.kcol', { has: p.locator('.khead span', { hasText: n }) })
  await col('Новый лид').locator('.kc', { hasText: 'Дана' }).waitFor()
  assert.strictEqual(await p.locator('.kc', { hasText: 'Чужой лид' }).count(), 0, 'чужие лиды МОП не видит')
  await noScroll(p)
  await p.screenshot({ path: `${shots}/lidy-1-kanban.png` })
  await col('Новый лид').locator('.kc', { hasText: 'Дана' }).dragTo(col('В работе'))
  await p.locator('.kbmsg', { hasText: 'Дана → «В работе»' }).waitFor()
  const up = (await bxCalls()).find(x => x.method === 'crm.lead.update')
  assert.strictEqual(up.params.fields.STATUS_ID, 'IN_PROCESS')
  await col('В работе').locator('.kc', { hasText: 'Дана' }).waitFor()
  await p.screenshot({ path: `${shots}/lidy-2-perenos.png` })

  // телефон: статусы кнопками, карточки во всю ширину
  const t = await open(b, 6100)
  await tab(t, 'Лиды')
  await t.locator('.kstages').waitFor()
  assert.strictEqual(await t.locator('.kb').count(), 0, 'на телефоне без колонок')
  await t.locator('.kstages button', { hasText: 'В работе' }).click()
  await t.locator('.kphone .kc', { hasText: 'Дана' }).waitFor()
  await noScroll(t)
  await t.screenshot({ path: `${shots}/lidy-3-telefon.png` })
  await t.locator('.kphone .kc', { hasText: 'Дана' }).click()
  await t.getByText('Дана').first().waitFor()
  await b.close()
  console.log('lidy: ok')
})().catch(e => { console.error(e); process.exit(1) })

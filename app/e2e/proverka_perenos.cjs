// Сквозной тест (HEAD 15.11): «Перенести на другой объект» прямо в «Проверке» (в т. ч. из «Без объекта»)
// и личная ставка в час в «Команде». API — e2e/fake_api.py.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = '/home/user/artgame-app/app/backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const shots = process.env.SHOTS || '/var/tmp'
const psql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "${q}"`)

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 } })
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
  const a = (await call(6500, '/register', { full_name: 'Әсел Мұнайдар' })).id
  await call(1000, `/people/${a}`, { role_code: 'artist', zones: ['mural'] })
  psql("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1283, 'КАРТИНЫ 60 ШТ ЭЛЬМОНТЕ БИАЙ', 'Алматы', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")
  psql(`INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, status, backfill, work_done) VALUES (gen_random_uuid(), ${a}, 0, 'mural', now() - interval '1 days', now() - interval '1 days' + interval '11 hours', 'submitted', true, 'Покраска рамок морилкой (в 4 слоя)')`)
  const h = await open(b, 1000)
  await tab(h, 'Проверка')
  const row = h.locator('.row', { hasText: 'Покраска рамок' }).first(); await row.waitFor()
  await row.scrollIntoViewIfNeeded(); await h.screenshot({ path: `${shots}/proverka-perenos-0.png` })
  await row.getByText('Перенести на другой объект').click()
  await row.locator('.moveshift select').selectOption('1283')
  await h.screenshot({ path: `${shots}/proverka-perenos-1.png` })
  await row.getByRole('button', { name: 'Перенести смену и фото' }).click()
  await h.getByText(/Перенесено: №1283/).waitFor()
  await h.screenshot({ path: `${shots}/proverka-perenos-2.png` })
  await h.locator('.row', { hasText: 'КАРТИНЫ 60 ШТ' }).first().waitFor()
  await tab(h, 'Команда')
  const pr = h.locator('.prow', { hasText: 'Әсел' }).first()
  if (!await pr.isVisible().catch(() => false)) await h.locator('.head', { hasText: 'Роспись' }).first().click()
  await pr.click()
  const inp = h.locator('input[placeholder="по ставкам роли"]'); await inp.waitFor()
  await inp.fill('1200'); await inp.blur(); await h.waitForTimeout(800)
  await inp.scrollIntoViewIfNeeded(); await h.screenshot({ path: `${shots}/komanda-stavka-chas.png` })
  const r = await call(1000, '/people'); assert.equal(+r.find(x => x.id === a).hour_rate, 1200)
  console.log('OK review move + hour rate')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

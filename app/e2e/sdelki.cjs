// Сквозной тест «Сделки МОП»: HEAD связывает МОП с Битриксом, МОП видит свои сделки и открывает их в КП и «Документах».
// API — e2e/fake_api.py (Битрикс подменён ответами из tests/test_bx.py), с ARTGAME_CONTENT_KEY; экран — vite preview :4173.
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

async function open(b, id, vp) {
  const ctx = await b.newContext({ viewport: vp || { width: 390, height: 800 } })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.goto('http://127.0.0.1:4173/')
  return p
}
const mopFrame = p => p.frames().find(f => f.url().includes('/api/p/mop/'))

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const m = await call(6000, '/register', { full_name: 'Ануар' })
  await call(1000, `/people/${m.id}`, { role_code: 'mop', zones: ['sales'] })

  // HEAD: связывает МОП с пользователем Битрикса во вкладке «Команда»
  const h = await open(b, 1000)
  await h.getByRole('button', { name: 'Команда' }).click()
  const sel = h.locator('.person', { hasText: 'Ануар' }).locator('label select')
  await sel.selectOption({ label: 'Ануар Минкеев' })
  await h.waitForTimeout(500)
  assert.strictEqual((await call(1000, '/people')).find(x => x.id === m.id).bitrix_user_id, 4565)
  await h.getByRole('button', { name: 'Сделки' }).click()
  await h.locator('.deal').first().waitFor()
  assert.strictEqual(await h.locator('.deal').count(), 2, 'HEAD видит все открытые сделки')

  // МОП: только свои сделки
  const p = await open(b, 6000)
  await p.getByRole('button', { name: 'Сделки' }).click()
  await p.locator('.deal').first().waitFor()
  assert.strictEqual(await p.locator('.deal').count(), 1)
  assert.match(await p.locator('.deal').first().textContent(), /1601.*КАФЕ/)
  await p.screenshot({ path: `${shots}/sdelki-list.png` })

  // «Документы»: клиент, контакты, адрес из сделки
  await p.locator('.deal').first().getByRole('button', { name: 'Документы' }).click()
  await p.waitForFunction(() => /заполнено/.test(document.querySelector('iframe.placeframe')?.contentDocument?.querySelector('#app .agbx-st')?.textContent || ''), null, { timeout: 20000 })
  const ds = await mopFrame(p).evaluate(() => ({ num: DS.num, cname: DS.cname, ctype: DS.ctype, ctel: DS.ctel, cmail: DS.cmail, objAddr: DS.objAddr }))
  assert.deepStrictEqual(ds, { num: '1601', cname: 'ТОО «Ромашка»', ctype: 'ТОО', ctel: '+77001112233', cmail: 'a@x.kz', objAddr: 'Астана, ул. Достык 5' })
  await mopFrame(p).locator('#app .agbx').scrollIntoViewIfNeeded()
  await p.screenshot({ path: `${shots}/sdelki-docs.png` })

  // «КП»: номер сделки → штатная кнопка «Подтянуть» страницы через сервер
  await p.getByRole('button', { name: 'Сделки' }).click()
  await p.locator('.deal').first().getByRole('button', { name: 'КП' }).click()
  await p.waitForFunction(() => /загружена/.test(document.querySelector('iframe.placeframe')?.contentDocument?.getElementById('crmStatus')?.textContent || ''), null, { timeout: 20000 })
  const kp = await mopFrame(p).evaluate(() => ({ client: document.getElementById('client').value, object: document.getElementById('object').value }))
  assert.strictEqual(kp.client, 'ТОО «Ромашка»')
  assert.match(kp.object, /Астана/)
  await mopFrame(p).locator('#crmStatus').scrollIntoViewIfNeeded()
  await p.screenshot({ path: `${shots}/sdelki-kp.png` })
  // в КП есть выбор из своих сделок
  assert.ok(await mopFrame(p).locator('#kpgen .agbx select option').count() >= 2)
  console.log('OK: связка в «Команде», свои сделки, подтяжка в КП и «Документы»')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

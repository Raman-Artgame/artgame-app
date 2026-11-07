// Сквозной тест «Рабочие места»: HEAD и художник открывают места из артефактов внутри приложения.
// Нужен API с ARTGAME_CONTENT_KEY (ключ к app/backend/places/*.enc) — см. app/README.md.
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

async function open(b, id, vp, name = 'Место') {
  const ctx = await b.newContext({ viewport: vp || { width: 390, height: 780 } })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.goto('http://127.0.0.1:4173/')
  await tab(p, name)
  return { p, ctx }
}
const frame = p => p.frameLocator('iframe.placeframe')

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
  const a = await call(2100, '/register', { full_name: 'Художник' })
  await call(1000, `/people/${a.id}`, { role_code: 'artist', zones: ['mural'] })

  // HEAD: места художников, печати и дизайна (рабочее место МОП живёт в карточке сделки и в «Учёбе», калькулятор — один, в МОП)
  const { p } = await open(b, 1000, { width: 1280, height: 860 })
  const chips = await p.locator('.place .chips button').allTextContents()
  assert.deepStrictEqual(chips, ['Художники', 'Печать', 'Дизайн'])
  for (const [chip, title] of [['Художники', 'Рабочее место художников'], ['Печать', 'Рабочее место печати'], ['Дизайн', 'Рабочее место дизайнера']]) {
    await p.locator('.place .chips button', { hasText: chip }).click()
    await p.waitForFunction(t => document.querySelector('iframe.placeframe')?.contentDocument?.title?.startsWith(t), title, { timeout: 15000 })
    await p.waitForTimeout(1200)
    await p.screenshot({ path: `${shots}/place-${chip}.png` })
  }
  // Дизайн: общая доска на нашей базе (не «только в этом браузере»)
  await p.waitForTimeout(1500)
  const fr = p.frames().find(f => f.url().includes('/api/p/dz/'))
  const local = await fr.evaluate(() => typeof LOCAL !== 'undefined' && LOCAL)
  assert.strictEqual(local, false, 'доска дизайна должна работать через сервер')
  const saved = await fr.evaluate(async () => { await save1({ id: 'e2e1', deal: '731', obj: 'Кафе e2e', stage: 0, cat: 'M', method: 'роспись', who: 'Тест' }); return true })
  assert.ok(saved)
  const docs = await fr.evaluate(() => fetch(location.pathname.replace(/\/index\.html$/, '') + '/_db/projects').then(r => r.json()))
  assert.strictEqual(docs.docs[0].data.obj, 'Кафе e2e')
  // ссылка из «Печати» на «Художников» открывает место в приложении
  await p.locator('.place .chips button', { hasText: 'Печать' }).click()
  await p.waitForFunction(() => document.querySelector('iframe.placeframe')?.contentDocument?.title?.startsWith('Рабочее место печати'))
  // ссылки на артефакт художников есть в разделах печати; проверяем механизм на такой же ссылке
  const pf = p.frames().find(f => f.url().includes('/api/p/print/'))
  await pf.evaluate(() => { const a = document.createElement('a'); a.href = 'https://claude.ai/artifact/AUsM36vXPoSqk6J4LQUZqj#gip'; a.textContent = 'x'; document.body.appendChild(a); a.click() })
  await p.waitForFunction(() => document.querySelector('iframe.placeframe')?.contentDocument?.title?.startsWith('Рабочее место художников'))

  // Художник (кабинеты HEAD 07.11): место художников — это «Учёба» и должностная; «Оплата», «Рост», «Куратор/ГИП» скрыты
  const { p: pa } = await open(b, 2100, null, 'Учёба')
  assert.deepStrictEqual(await pa.locator('.place .chips button').allTextContents(), ['Художники', 'Должностная'])
  await pa.waitForFunction(() => document.querySelector('iframe.placeframe')?.contentDocument?.title?.startsWith('Рабочее место художников'))
  const af = () => pa.frames().find(f => f.url().includes('/api/p/art/'))
  await pa.waitForTimeout(800)
  assert.ok(af().url().includes('hide=pay%2Cgrow%2Cgip%2Cchief'), af().url())
  const vis = await af().evaluate(() => ['ucheb', 'pay', 'grow', 'gip'].map(h => [...document.querySelectorAll(`a[href="#${h}"]`)].some(a => a.offsetParent)))
  assert.deepStrictEqual(vis, [true, false, false, false])
  await af().evaluate(() => { location.hash = '#pay' })
  await pa.waitForTimeout(300)
  assert.strictEqual(await af().evaluate(() => location.hash), '#ucheb')
  await pa.locator('.place .chips button', { hasText: 'Должностная' }).click()
  await pa.getByText('Обязанности').waitFor()
  await pa.screenshot({ path: `${shots}/place-artist-duty.png` })
  await pa.locator('.place .chips button', { hasText: 'Художники' }).click()
  await pa.waitForFunction(() => document.querySelector('iframe.placeframe')?.contentDocument?.title?.startsWith('Рабочее место художников'))
  await pa.waitForTimeout(1200)
  await pa.screenshot({ path: `${shots}/place-artist-phone.png` })
  const urls = await call(2100, '/places')
  assert.deepStrictEqual(urls.map(x => x.code), ['art'])
  const mopUrl = urls[0].url.replace('/p/art/', '/p/mop/')
  assert.strictEqual((await fetch('http://127.0.0.1:8100' + mopUrl)).status, 403)
  console.log('OK: места открываются по ролям, доска дизайна на сервере, переходы между местами')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

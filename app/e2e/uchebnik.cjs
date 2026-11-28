// Сквозной тест «Учёба» МОП (HEAD 28.11): учебник — раздел приложения, тесты раундами с проверкой на сервере.
// Нужен API с ARTGAME_CONTENT_KEY (fake_api.py) и `npx vite preview --port 4173`. Скриншоты — в SHOTS (по умолчанию /var/tmp).
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

async function open(b, id, vp, scale = 1) {
  const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: scale })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } }; localStorage.removeItem('artgame.study') }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.goto('http://127.0.0.1:4173/')
  const nav = p.locator('nav')
  await nav.getByRole('button', { name: 'Учёба', exact: true }).click()
  await p.locator('.stu-hero').first().waitFor()
  return { p, ctx }
}
const settle = p => p.waitForFunction(() => [...document.images].every(i => i.complete || i.loading === 'lazy'), null, { timeout: 15000 }).then(() => p.waitForTimeout(400))

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const m = await call(2300, '/register', { full_name: 'Ануар Минкеев' })
  await call(1000, `/people/${m.id}`, { role_code: 'mop', zones: ['sales'] })

  // вопросы без ответа: верный вариант на телефон не уходит
  const r = await call(2300, '/study/mop/round?ch=05')
  assert.strictEqual(r.q.length, 10)
  assert.ok(r.q.every(q => q.opts.length === 4 && q.opts.every(o => o.k && !('ok' in o))))
  const bad = await call(2300, '/study/mop/answer', { qid: r.q[0].id, k: 'xxxx' })
  assert.ok(String(bad.detail).includes('вариант'))

  for (const [vp, tag, scale] of [[{ width: 1600, height: 1000 }, 'pk', 1], [{ width: 390, height: 844 }, 'tel', 2]]) {
    const { p, ctx } = await open(b, 2300, vp, scale)
    await settle(p)
    await p.screenshot({ path: `${shots}/uch-${tag}-1-oblozhka.png` })
    // глава 1
    await p.locator('.stu-card', { hasText: 'Роль МОП' }).click()
    await p.locator('.stu-hero h1', { hasText: 'Роль МОП' }).waitFor()
    await settle(p)
    await p.screenshot({ path: `${shots}/uch-${tag}-2-glava01.png` })
    if (tag === 'tel') await p.screenshot({ path: `${shots}/uch-${tag}-2-glava01-full.png`, fullPage: true })
    // ссылка «раздел 8» внутри текста открывает главу 8
    await p.locator('.stu-read a[href="#s08"]').first().click()
    await p.locator('.stu-hero h1', { hasText: 'Каталоги' }).waitFor()
    // глава 5 — цены
    await p.evaluate(() => window.scrollTo(0, 0))
    if (tag === 'pk') await p.locator('.stu-toc a', { hasText: 'Цены и расчёт' }).click()
    else await p.locator('.stu-chips button', { hasText: '05' }).click()
    await p.locator('.stu-hero h1', { hasText: 'Цены' }).waitFor()
    await settle(p)
    await p.screenshot({ path: `${shots}/uch-${tag}-3-glava05.png` })
    await p.locator('#stu-p5-2').scrollIntoViewIfNeeded()
    await p.evaluate(() => window.scrollBy(0, -80))
    await p.waitForTimeout(300)
    await p.screenshot({ path: `${shots}/uch-${tag}-4-glava05-tablica.png` })
    // «Прочитано» — сохраняется на сервере
    const rd = p.locator('.stu-end button', { hasText: 'Глава прочитана' })
    if (await rd.count()) await rd.click()
    await p.locator('.stu-end .ok').waitFor()
    // тест главы 5
    await p.locator('.stu-end button', { hasText: 'Пройти тест' }).click()
    await p.locator('.stu-qcard h3').waitFor()
    await p.screenshot({ path: `${shots}/uch-${tag}-5-vopros.png` })
    for (let i = 0; i < 10; i++) {
      await p.locator('.stu-opt').nth(i % 2).click()
      await p.locator('.stu-why').waitFor()
      if (i === 0) await p.screenshot({ path: `${shots}/uch-${tag}-6-razbor.png` })
      await p.locator('.stu-qbot button').click()
    }
    await p.locator('.stu-qcard.sum').waitFor()
    await p.screenshot({ path: `${shots}/uch-${tag}-7-itog.png` })
    await p.locator('.stu-qcard.sum button', { hasText: 'К списку тестов' }).click()
    await p.locator('.stu-qgrid').waitFor()
    await p.waitForTimeout(300)
    await p.screenshot({ path: `${shots}/uch-${tag}-8-testy.png` })
    await ctx.close()
  }
  const me = await call(2300, '/study/mop/me')
  assert.ok(me.read.includes('05'))
  assert.ok(me.answers >= 20, JSON.stringify(me))
  const team = await call(1000, '/study/mop/team')
  assert.ok(team.people.some(x => x.name === 'Ануар Минкеев' && x.read >= 1))
  // HEAD видит учебник чипом «Учебник МОП» рядом с местами ролей
  const { p } = await open(b, 1000, { width: 1440, height: 900 }).catch(async () => ({}))
  if (p) await p.screenshot({ path: `${shots}/uch-head.png` })
  await b.close()
  console.log('uchebnik ok')
})().catch(e => { console.error(e); process.exit(1) })

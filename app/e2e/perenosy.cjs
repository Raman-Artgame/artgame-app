// Переносы по буквам (HEAD 09.11: «Буквы запрыгали — везде перепроверить»): каждая роль, каждая вкладка, ширина iPhone 375.
// Слово (или сумма «5 000 ₸»), разорванное между строками, — ошибка. Нижняя панель — у нижнего края на любой странице.
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
const psql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "${q}"`)
const ROLES = [['support', ['mural']], ['artist', ['mural']], ['artist_pro', ['mural']], ['lead_artist', ['mural', 'print']], ['print_operator', ['print']],
  ['print_master', ['mural', 'print']], ['mop', ['sales']], ['lead_designer', ['design']], ['designer_asst', ['design']], ['carpenter', []], ['head', []]]

// слова, у которых буквы оказались на разных строках
const broken = () => {
  const out = []
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const el = n.parentElement
    if (!el || !el.offsetParent || getComputedStyle(el).visibility === 'hidden') continue
    const re = /[^\s ]{2,}|\d[\d\s ]*\d\s?₸/g
    for (let m; (m = re.exec(n.data));) {
      const r = document.createRange(); r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length)
      const tops = new Set([...r.getClientRects()].filter(x => x.width > 0).map(x => Math.round(x.top)))
      if (tops.size > 1 && !/[-–/]/.test(m[0])) out.push(m[0])
    }
  }
  // кнопки, вылезшие за край карточки или экрана (HEAD 09.11: ✓/✕ в «Проверке»)
  for (const btn of document.querySelectorAll('.card button, .row button')) {
    if (!btn.offsetParent) continue
    const r = btn.getBoundingClientRect(), c = (btn.closest('.card') || document.body).getBoundingClientRect()
    if (r.width && (r.right > c.right + 1 || r.right > innerWidth + 1)) out.push(`кнопка «${btn.textContent.trim().slice(0, 12)}» за краем`)
  }
  return [...new Set(out)]
}

;(async () => {
  psql("INSERT INTO objects (id, title, city, bitrix_stage, level, area_m2, address) VALUES (731, 'УЙДОМДОНЕР', 'Астана', 'UC_AV00QK', 'medium', 60, 'Мангилик Ел 1') ON CONFLICT (id) DO UPDATE SET bitrix_stage='UC_AV00QK'")
  psql("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1579, 'ДЕТСКАЯ ПЛОЩАДКА', 'Астана', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")
  await call(1000, '/register', { full_name: 'HEAD' })
  const az = await call(7099, '/register', { full_name: 'Ажар Длиннофамильная-Саппортова' })
  psql(`INSERT INTO shifts (client_uid, person_id, object_id, zone_code, started_at, ended_at, status, work_done) VALUES (gen_random_uuid(), ${az.id}, 731, 'mural', now() - interval '20 hours', now() - interval '2 hours', 'submitted', 'Фон, контур и детали на всей стене у входа')`)
  for (const [st, amt, why] of [['rejected', 480, "'Ошибка'"], ['approved', 32300, 'NULL'], ['submitted', 410, 'NULL']])
    psql(`INSERT INTO expenses (client_uid, person_id, object_id, category, amount, paid_by, note, status, reason) VALUES (gen_random_uuid(), ${az.id}, 0, 'stock_art', ${amt}, 'company', 'Колеровка, краска и материалы × 1 = ${amt} (нет ориентира) · Жана Айгерим', '${st}', ${why})`)
  const b = await chromium.launch()
  const bad = [], checked = []
  let tg = 7100
  for (const [role, zones] of ROLES) {
    const id = role === 'head' ? 1000 : tg++
    if (role !== 'head') {
      const p = await call(id, '/register', { full_name: 'Владимир Тестов' })
      await call(1000, `/people/${p.id}`, { role_code: role, zones })
    }
    const ctx = await b.newContext({ viewport: { width: 375, height: 700 } })
    const pg = await ctx.newPage()
    const d = sign(id)
    await pg.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
    await pg.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
    pg.on('dialog', dl => dl.dismiss())
    await pg.goto('http://127.0.0.1:4173/')
    await pg.locator('nav').waitFor()
    const n = await pg.locator('nav button').count()
    const more = n && (await pg.locator('nav button').nth(n - 1).textContent()) === 'Ещё'
    const extra = more ? await (async () => { await pg.locator('nav button').nth(n - 1).click(); await pg.waitForTimeout(300)
      const t = await pg.locator('.sheetbox button').allTextContents(); await pg.mouse.click(5, 5); await pg.waitForTimeout(200); return t })() : []
    for (let i = 0; i < n + extra.length - (more ? 1 : 0); i++) {
      let name
      if (i < n - (more ? 1 : 0)) {
        const btn = pg.locator('nav button').nth(i)
        name = (await btn.textContent()).replace(/\d+$/, '')
        await btn.click()
      } else {   // пункты листа «Ещё»
        name = extra[i - (n - 1)]
        await pg.locator('nav button').nth(n - 1).click(); await pg.waitForTimeout(300)
        await pg.locator('.sheetbox button', { hasText: name }).first().click()
      }
      await pg.waitForTimeout(700)
      let w = await pg.evaluate(broken)
      const subs = await pg.locator('.segf button').allTextContents()   // подвкладки (Финансы: Обзор…Люди)
      for (let j = 1; j < subs.length; j++) {
        const sname = subs[j]
        if (await pg.locator('.segf button').count() <= j) break
        await pg.locator('.segf button').nth(j).click(); await pg.waitForTimeout(600)
        const ws = await pg.evaluate(broken)
        if (ws.length) w = w.concat(ws.map(x => `${sname}: ${x}`))
        if (role === 'head' && sname === 'Закупки') await pg.screenshot({ path: `${shots}/nav-${role}-${name}-${sname}.png`, fullPage: true })
      }
      if (subs.length > 1) { await pg.locator('.segf button').first().click(); await pg.waitForTimeout(300) }
      for (const f of pg.frames().slice(1)) w = w.concat(await f.evaluate(broken).catch(() => []))   // места ролей (учебник, ТБ) во фрейме
      if (name === 'Проекты' && await pg.locator('.pcard').first().isVisible().catch(() => false)) {   // и карточка проекта
        await pg.locator('.pcard').first().click(); await pg.waitForTimeout(700); w = w.concat(await pg.evaluate(broken))
        await pg.getByRole('button', { name: '← Проекты' }).click().catch(() => {})
      }
      if (w.length) { bad.push(`${role} · ${name}: ${w.slice(0, 6).join(', ')}`); await pg.screenshot({ path: `${shots}/wrap-${role}-${i}.png`, fullPage: true }) }
      // панель у нижнего края: и вверху страницы, и прокрутив до конца (короткая и длинная страница)
      for (const end of [false, true]) {
        if (end) await pg.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
        await pg.waitForTimeout(150)
        const nav = await pg.locator('nav').boundingBox()
        assert(Math.abs(nav.y + nav.height - 700) < 2, `${role} · ${name}: панель не у нижнего края (${nav.y + nav.height})`)
      }
      const tall = await pg.evaluate(() => document.documentElement.scrollHeight)
      checked.push(`${role}·${name}:${tall > 700 ? 'длинная' : 'короткая'}`)
      if ((role === 'head' && name === 'Проверка') || (role === 'print_master' && ['Сбор', 'Кабинет'].includes(name)))
        await pg.screenshot({ path: `${shots}/nav-${role}-${name}.png` })
      await pg.evaluate(() => window.scrollTo(0, 0))
    }
    await ctx.close()
  }
  await b.close()
  if (bad.length) { console.log(bad.join('\n')); process.exit(1) }
  console.log(`OK: переносов по буквам нет, нижняя панель у края — 11 ролей, ${checked.length} вкладок (коротких ${checked.filter(x => x.endsWith('короткая')).length}, длинных ${checked.filter(x => x.endsWith('длинная')).length}), 375 px`)
})().catch(e => { console.error(e); process.exit(1) })

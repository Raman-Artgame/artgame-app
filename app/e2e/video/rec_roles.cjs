// Запись экранов для обучающих роликов по ролям (HEAD 08.11). Каждая сцена держится не меньше длины своей озвучки.
// node rec_roles.cjs <роль> <папка записи> <durations.json> <папка с фото>   (стенд: fake_api.py + vite preview, база чистая)
const { chromium } = require('playwright')
const fs = require('fs')
const { seed, open, tab, call } = require('./common.cjs')
const [ROLE, OUT, DURS, IMG] = process.argv.slice(2)
const R = JSON.parse(fs.readFileSync(__dirname + '/scripts.json', 'utf8'))[ROLE]
const DUR = JSON.parse(fs.readFileSync(DURS, 'utf8'))[ROLE]
const W = (p, ms) => p.waitForTimeout(ms)
const BEFORE = IMG + '/wall1.jpg', AFTER = IMG + '/s05.jpg', CHEK = __dirname + '/../chek.png'
const scroll = async (p, y, ms = 1300) => { await p.evaluate(y => window.scrollTo({ top: y, behavior: 'smooth' }), y); await W(p, ms) }
const scrollTo = async (p, loc, ms = 1200) => { await loc.first().evaluate(e => e.scrollIntoView({ behavior: 'smooth', block: 'center' })); await W(p, ms) }
const typeIn = (loc, t, d = 70) => loc.pressSequentially(t, { delay: d })
const has = async loc => (await loc.count()) > 0

const OBJ = { mural: '№731', print: '№812' }
async function pickObj(p, z) {
  const b = p.locator('.objpick button, button', { hasText: OBJ[z] }).first()
  await b.waitFor({ timeout: 8000 }); await b.click(); await W(p, 1200)
}
async function startShift(p, z) {
  await tab(p, 'Смена'); await W(p, 500)
  if (await has(p.getByText('Смена идёт'))) return
  await pickObj(p, z)
  const snap = p.locator('.snap input[type=file]').first()
  await scrollTo(p, p.locator('.snap'))
  await snap.setInputFiles(BEFORE); await p.locator('.snap img').first().waitFor(); await W(p, 1300)
  const go = p.getByRole('button', { name: 'Начать смену' })
  await scrollTo(p, go, 800); await go.click()
  await p.getByText('Смена идёт').first().waitFor(); await W(p, 800); await scroll(p, 0, 900)
}
async function finishShift(p, m2 = '12') {
  const a = p.locator('input[inputmode=decimal]').first()
  await scrollTo(p, a, 900); await typeIn(a, m2, 160)
  const t = p.locator('textarea').first(); await typeIn(t, 'Перенёс эскиз и расписал фон', 35)
  await scrollTo(p, p.locator('.snap'), 800)
  await p.locator('.snap input[type=file]').first().setInputFiles(AFTER); await p.locator('.snap img').first().waitFor(); await W(p, 1200)
  const fin = p.getByRole('button', { name: 'Закончить и отправить на проверку' })
  await scrollTo(p, fin, 700); await fin.click()
  await p.getByText('Смена закончена').first().waitFor({ timeout: 8000 }).catch(() => {}); await W(p, 1200)
}
async function expense(p) {
  await tab(p, 'Расход'); await W(p, 1000)
  const sum = p.locator('input[inputmode=numeric]').first()
  await sum.click(); await typeIn(sum, '4500', 140)
  const note = p.getByPlaceholder('Комментарий'); if (await has(note)) await typeIn(note.first(), 'Такси с материалом', 40)
  const f = p.locator('input[type=file]').first(); await scrollTo(p, p.getByText('Фото чека'), 700)
  await f.setInputFiles(IMG + '/receipt.png'); await p.locator('.photo img').first().waitFor(); await W(p, 1000)
  const send = p.getByRole('button', { name: 'Отправить расход' }); await scrollTo(p, send, 700); await send.click(); await W(p, 1500)
  if (!process.env.PRE) { await tab(p, 'Кабинет').catch(() => {}); await W(p, 1200); const my = p.getByText('Мои расходы').first(); if (await has(my)) await scrollTo(p, my, 1500) }
}
async function study(p, extra = ['ТБ', 'Правила игры']) {
  await tab(p, 'Учёба'); await W(p, 1200)
  await p.waitForFunction(() => { const f = document.querySelector('iframe'); return !f || (f.contentDocument && f.contentDocument.body && f.contentDocument.body.innerText.length > 50) }, null, { timeout: 15000 }).catch(() => {})
  await W(p, 1500)
  const fr = p.frames().find(f => f !== p.mainFrame())
  if (fr) { await fr.evaluate(() => window.scrollTo({ top: 600, behavior: 'smooth' })).catch(() => {}); await W(p, 2000); await fr.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })).catch(() => {}); await W(p, 900) }
  else { await scroll(p, 500, 1600); await scroll(p, 0, 900) }
  for (const name of extra) {
    const b = p.getByRole('button', { name, exact: true }).first()
    if (await has(b)) { await b.click(); await W(p, 1500); await scroll(p, 450, 1500); await scroll(p, 0, 700) }
  }
}
async function cabinet(p) {
  await tab(p, 'Кабинет'); await W(p, 1500)
  await scroll(p, 420, 1800); await scroll(p, 900, 1800)
  const open = p.getByRole('button', { name: 'Открыть' }).first()
  if (await has(open)) { await scrollTo(p, open, 900); await open.click(); await W(p, 1500); await scroll(p, 1400, 1800) }
}
async function review(p) {
  await tab(p, 'Проверка'); await W(p, 1500)
  await scroll(p, 300, 1500)
  const ok = p.getByRole('button', { name: '✓' }).first()
  if (await has(ok)) { await scrollTo(p, ok, 900); await ok.click(); await W(p, 1500) }
  await scroll(p, 0, 800)
}
async function kit(p, z) {
  await tab(p, 'Сбор'); await W(p, 1300)
  const row = p.locator('.kitobj', { hasText: OBJ[z] }).first()
  await scrollTo(p, row, 900)
  await row.getByRole('button', { name: z === 'print' ? /Печать/ : /Роспись/ }).first().click(); await W(p, 1300)
  if (z === 'mural' && await has(p.getByRole('button', { name: '+ цвет' }))) {
    await p.getByRole('button', { name: '+ цвет' }).click()
    const ar = p.locator('.kitrow2').first(); await typeIn(ar.locator('input').nth(0), 'RAL 3020', 60)
    await ar.locator('.stepper input').fill('5'); await W(p, 400); await ar.getByRole('button', { name: 'больше' }).click(); await W(p, 700)
  }
  const taps = p.locator('.tap')
  for (let i = 0; i < Math.min(2, await taps.count()); i++) { await scrollTo(p, taps.nth(i), 700); await taps.nth(i).click(); await W(p, 700) }
  await scroll(p, 1400, 1600)
}
async function prod(p, z) {
  await tab(p, 'Продакшн'); await W(p, 1300)
  await pickObj(p, z)
  const f = p.locator('label input[type=file]').first()
  await scrollTo(p, p.getByText(/Выбрать/).first(), 800)
  await f.setInputFiles([AFTER, IMG + '/s02.jpg']); await W(p, 2500)
  const mine = p.getByRole('button', { name: 'Моё', exact: true }); if (await has(mine)) { await mine.click(); await W(p, 1800) }
}

// ---- МОП (как в rec.cjs) ----
const step = (p, name) => p.locator('.hero .steps > div', { hasText: name }).click()
const MOP = {
  async today(p) { await p.locator('.bucket').first().waitFor(); await W(p, 2500); await scroll(p, 420, 2200); await scroll(p, 0, 900) },
  async lead(p) {
    await tab(p, 'Лиды'); await p.locator('.qrow', { hasText: 'Дана' }).waitFor(); await W(p, 1500)
    await p.locator('.qrow', { hasText: 'Дана' }).click(); await p.locator('h3', { hasText: 'В сделку' }).waitFor(); await W(p, 1200)
    await scrollTo(p, p.locator('h3', { hasText: 'В сделку' }), 1000)
    await typeIn(p.getByRole('textbox', { name: 'Объект', exact: true }), 'Школа №12', 70); await W(p, 400)
    await p.locator('.citypick .chips button', { hasText: 'Астана' }).click(); await W(p, 700)
    await p.locator('label', { hasText: 'Услуга' }).locator('select').selectOption({ label: 'Художественная роспись стен' })
    await p.locator('text=Всё есть — можно в сделку.').waitFor(); await W(p, 900)
    const go = p.getByRole('button', { name: 'В сделку', exact: true }); await scrollTo(p, go, 700); await go.click()
    await p.locator('.hero h2', { hasText: '№ 9100' }).waitFor(); await W(p, 1000)
  },
  async deal(p) {
    await tab(p, 'Сделки'); await p.locator('.stage .qrow').first().waitFor(); await W(p, 1200)
    const all = p.getByRole('button', { name: /^Все\s*\d*$/ }).first(); if (await has(all)) { await all.click(); await W(p, 1000) }
    await p.locator('.qrow', { hasText: '1601' }).first().click(); await p.locator('.hero .steps').waitFor(); await W(p, 2500)
    await scroll(p, 350, 1500)
  },
  async calc(p) {
    const calc = p.locator('.card', { has: p.locator('h3', { hasText: 'Расчёт' }) })
    await scrollTo(p, calc)
    const a = calc.locator('input[type=number]').first(); await a.fill(''); await typeIn(a, '60', 150); await W(p, 900)
    await calc.locator('.chips button', { hasText: 'Лак' }).click(); await W(p, 900)
    await scrollTo(p, calc.locator('.two'), 1000)
    const b = calc.getByRole('button', { name: 'Записать в сделку' }); await scrollTo(p, b, 600); await b.click(); await W(p, 1200)
  },
  async lock(p) {
    await scroll(p, 0, 800); await step(p, 'Договор'); await p.locator('.lockbox').waitFor(); await scrollTo(p, p.locator('.lockbox'), 2000)
    await scroll(p, 0, 700)
    await p.locator('.hero').getByRole('button', { name: 'Стадия' }).click()
    await p.locator('.sheetbox select').selectOption('LOSE'); await W(p, 2200)
    await p.locator('.sheetbox .x').click(); await W(p, 500)
  },
  async projects(p) { await tab(p, 'Проекты'); await W(p, 1500); const c = p.locator('.pcard').first(); if (await has(c)) { await c.click(); await W(p, 2000) } },
  async month(p) {
    await tab(p, 'Месяц'); await p.locator('h3', { hasText: 'Мои закрытые сделки' }).waitFor().catch(() => {}); await W(p, 2000)
    const sp = p.locator('.card', { hasText: 'Мои траты' }); if (await has(sp)) await scrollTo(p, sp, 2000)
  },
}

// ---- дизайн ----
const DZ = {
  async dz(p) { await tab(p, 'Дизайн'); await W(p, 1500); await scroll(p, 500, 2000); await scroll(p, 1000, 2000); await scroll(p, 0, 900) },
  async dzcard(p) {
    const c = p.locator('.dzstage .dzcard', { hasText: 'Дизайн кафе' }).first(); await scrollTo(p, c); await c.click(); await W(p, 1000)
    await p.locator('.modal select').nth(1).selectOption({ label: 'Мира' }).catch(() => p.locator('.modal select').nth(1).selectOption({ index: 1 }))
    await W(p, 700); await p.locator('.modal .chips button', { hasText: 'S' }).first().click(); await W(p, 600)
    await p.locator('.modal input[type=date]').fill('2026-11-14'); await W(p, 900)
    await p.getByRole('button', { name: 'Сохранить в Битрикс' }).click(); await W(p, 1600)
  },
  async dzopen(p) {
    const c = p.locator('.dzcard').first(); await scrollTo(p, c); await c.click(); await W(p, 2500)
    const m = p.locator('.modal'); if (await has(m)) { await m.evaluate(e => e.scrollTo({ top: 500, behavior: 'smooth' })).catch(() => {}); await W(p, 1800)
      const x = p.locator('.modal .x').first(); if (await has(x)) await x.click(); else await p.keyboard.press('Escape') }
    await W(p, 500)
  },
  async units(p) { await scroll(p, 0, 500); await p.getByRole('button', { name: 'Единицы' }).click(); await W(p, 2200); await scroll(p, 400, 1500) },
  async catalogs(p) { await scroll(p, 0, 500); await p.getByRole('button', { name: 'Каталоги' }).click(); await W(p, 2200) },
  async catalog_new(p) {
    await tab(p, 'Дизайн'); await scroll(p, 0, 500); await p.getByRole('button', { name: 'Каталоги' }).click(); await W(p, 1000)
    await p.getByRole('button', { name: '+ Новый' }).click(); await W(p, 600)
    await typeIn(p.getByPlaceholder('Название'), 'Лофт и бетон', 60)
    const st = p.getByPlaceholder('Стиль'); if (await has(st)) await typeIn(st, 'Лофт', 60)
    await typeIn(p.getByPlaceholder('Ссылка на папку или рефборд'), 'https://drive.google.com/drive/loft', 25)
    await p.getByRole('button', { name: 'Сохранить' }).click(); await W(p, 1200)
    await p.getByRole('button', { name: 'Отправить HEAD' }).click().catch(() => {}); await W(p, 1500)
  },
}

// ---- HEAD ----
const HEAD = {
  async pulse(p) { await W(p, 2000); await scroll(p, 500, 2000); await scroll(p, 1000, 1800); await scroll(p, 0, 900) },
  async deals(p) { await tab(p, 'Сделки'); await W(p, 2200); await scroll(p, 400, 1500) },
  async fin(p) { await tab(p, 'Финансы'); await W(p, 2000); await scroll(p, 500, 1800); await scroll(p, 0, 800) },
  async team(p) { await tab(p, 'Команда'); await W(p, 1800); await scroll(p, 500, 1800); await scroll(p, 0, 800) },
  async viewas(p) { await tab(p, 'Смотреть как'); await W(p, 2000); await scroll(p, 500, 1800) },
}

const ZONE = ['print_operator', 'print_master'].includes(ROLE) ? 'print' : 'mural'
const ACTS = {
  intro: async p => { await tab(p, 'Смена').catch(() => {}); await W(p, 2500) },
  intro_dz: async p => { await tab(p, 'Дизайн'); await W(p, 2500) },
  object: async p => { await tab(p, 'Смена'); await W(p, 600); await pickObj(p, ZONE); await scrollTo(p, p.locator('.promo'), 1800); await scroll(p, 900, 1800) },
  object_print: async p => ACTS.object(p),
  hints: async p => {
    const h = p.getByText('Перед началом').first(); await scrollTo(p, h)
    const cb = p.locator('input[type=checkbox]'); for (let i = 0; i < Math.min(3, await cb.count()); i++) { await cb.nth(i).click({ force: true }).catch(() => {}); await W(p, 800) }
    await scroll(p, 0, 900)
  },
  start: async p => startShift(p, ZONE), start_print: async p => startShift(p, ZONE),
  finish: async p => finishShift(p),
  expense, study: p => study(p, ROLE === 'support' ? ['ТБ', 'Правила игры'] : ROLE.includes('design') ? ['Обучение', 'Бренд'] : ['ТБ', 'Правила игры']),
  cabinet, review, kit: p => kit(p, ZONE), prod: p => prod(p, ZONE),
  projects: async p => MOP.projects(p),
  outro: async p => { await tab(p, R.scenes[0].act === 'today' ? 'Сегодня' : ROLE.includes('design') ? 'Дизайн' : ROLE === 'head' ? 'Пульт' : 'Смена').catch(() => {}); await scroll(p, 0, 500); await W(p, 1500) },
  ...MOP, ...DZ, ...HEAD,
}
ACTS.projects = MOP.projects; ACTS.review = review

// подготовка: чужая смена/расход ждут проверки, задача у помощника
async function pre(b) {
  const who = R.pre === 'review' || R.pre === 'head' ? R.people[0] : R.pre === 'review_print' ? 5000 : null
  if (who) {
    const z = R.pre === 'review_print' ? 'print' : 'mural'
    const { p, ctx } = await open(b, who)
    process.env.PRE = '1'; await startShift(p, z); await finishShift(p, '11'); await expense(p); delete process.env.PRE; await ctx.close()
  }
  if (R.pre === 'assign') {
    const { p, ctx } = await open(b, 7000); await tab(p, 'Дизайн'); await W(p, 800); await DZ.dzcard(p); await ctx.close()
  }
}

;(async () => {
  await seed(R.people.concat([R.tg]))
  const b = await chromium.launch()
  await pre(b)
  const t0 = Date.now(); const marks = []   // запись видео идёт с создания страницы — от этой точки
  const { p, ctx } = await open(b, R.tg, OUT)
  await W(p, 600)
  for (let i = 0; i < R.scenes.length; i++) {
    const sc = R.scenes[i], s = (Date.now() - t0) / 1000
    try { await ACTS[sc.act](p) } catch (e) { console.error('сцена', i, sc.act, e.message.split('\n')[0]); await p.screenshot({ path: `${OUT}/fail-${i}.png` }) }
    const need = (DUR[i] + 0.7) * 1000 - (Date.now() - t0 - s * 1000)
    if (need > 0) await W(p, need)
    marks.push([s, (Date.now() - t0) / 1000])
  }
  await p.__stopRec(); await ctx.close(); await b.close()
  fs.writeFileSync(OUT + '/marks.json', JSON.stringify(marks)); fs.writeFileSync(OUT + '/t0.json', JSON.stringify(t0 / 1000))
  console.log('ok', ROLE, marks.at(-1)[1])
})().catch(e => { console.error(e); process.exit(1) })

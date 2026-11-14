// Сквозной тест «Закрытие сделки через HEAD» (HEAD 12.11 «Да, по рекомендациям»). ГИП отмечает «Работы сданы» в карточке проекта;
// МОП со стадии «Оплата+закрывающие документы» видит 12 пунктов (их проверяет приложение, руками ничего не отмечают; 12-й —
// Продакшн: фото или видео, утверждённые HEAD, HEAD 12.11) и жмёт
// «На закрытие» — только когда всё выполнено; в «Оплата получена» сам перевести не может. HEAD: заявка на Пульте и в боте,
// паспорт сделки (деньги, затраты, прибыль и маржа рядом с нормой, флаги, документы и фото), «Вернуть» с причиной и «Закрыть»
// (сделка → «Оплата получена» + «Окончание факт», паспорт снимком, PDF в «ДОКУМЕНТЫ»). Закрытый объект не принимает смены;
// сделка, закрытая в Битриксе мимо паспорта, — красным на Пульте. Закрыть (и принять закрытую мимо паспорта) — только когда выполнены
// все пункты (HEAD 12.11), иначе только «Вернуть». API — e2e/fake_api.py на пустой базе. Экраны 390×800.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const crypto = require('crypto')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const SIG = {}
const sign = id => SIG[id] || (SIG[id] = execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim())
const act = async (p, name) => { const b = p.locator('.hero').getByRole('button', { name, exact: true }); if (!(await b.count())) await p.locator('.hero .morebtn').click(); await b.first().click() }   // редкие действия — под «Ещё действия» (HEAD 14.11)
const API = 'http://127.0.0.1:8100/api'
const req = async (id, path, body) => { const r = await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) }); return { status: r.status, body: await r.json() } }
const call = async (id, path, body) => { const r = await req(id, path, body); assert.ok(r.status < 300, `${path}: ${r.status} ${JSON.stringify(r.body)}`); return r.body }
const e2e = (path, body) => fetch(API + '/_e2e' + path, { method: body ? 'POST' : 'GET', headers: { 'Content-Type': 'application/json' },
  body: body && JSON.stringify(body) }).then(r => r.json())
const psql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qtAc "${q}"`).toString().trim()
const shots = process.env.SHOTS || '/var/tmp'
const CHEK = 'data:image/png;base64,' + require('fs').readFileSync(__dirname + '/chek.png').toString('base64')
const uid = () => crypto.randomUUID()
const day = n => new Date(Date.now() + n * 86400000).toLocaleDateString('en-CA', { timeZone: 'Asia/Almaty' })
const dmy = s => s.split('-').reverse().join('.')
const FILE = [{ id: 11, downloadUrl: 'https://fake.bitrix24.kz/file' }]

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 800 }, timezoneId: 'Asia/Almaty', locale: 'ru-RU' })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {}, openLink() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.route('https://fonts.googleapis.com/**', r => r.fulfill({ body: '', contentType: 'text/css' }))
  p.on('dialog', dl => dl.accept())
  p.on('pageerror', e => { throw e })
  await p.goto('http://127.0.0.1:4173/')
  return p
}
async function tab(p, name) {
  const nav = p.locator('nav')
  const re = new RegExp(`^${name}\\s*\\d*$`)
  await nav.locator('button').first().waitFor()
  if (await nav.getByRole('button', { name: re }).waitFor({ timeout: 1500 }).then(() => true, () => false)) return nav.getByRole('button', { name: re }).click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}
// На ширине iPhone ничего не вылезает вбок (HEAD 09.11)
// Снимок экрана; loc — один блок целиком, full — вся страница (нижнее меню на время снимка прячем, чтобы не легло поверх)
async function shot(p, name, loc, full) {
  if (!loc && !full) return p.screenshot({ path: `${shots}/${name}.png` })
  await p.evaluate(() => { document.querySelector('nav').style.visibility = 'hidden' })
  await (loc ? loc.screenshot({ path: `${shots}/${name}.png` }) : p.screenshot({ path: `${shots}/${name}.png`, fullPage: true }))
  await p.evaluate(() => { document.querySelector('nav').style.visibility = '' })
}
const fits = async (p, what) => assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `${what}: страница шире экрана`)
// Фото «с объекта» для паспорта: рисуются в браузере, без файлов
const art = (p, n) => p.evaluate(n => {
  const c = document.createElement('canvas'); c.width = 640; c.height = 480
  const g = c.getContext('2d'), h = [[350, 20], [200, 250], [40, 120], [280, 330]][n % 4]
  const gr = g.createLinearGradient(0, 0, 640, 480)
  gr.addColorStop(0, `hsl(${h[0]} 70% 55%)`); gr.addColorStop(1, `hsl(${h[1]} 60% 30%)`)
  g.fillStyle = gr; g.fillRect(0, 0, 640, 480)
  for (let i = 0; i < 9; i++) { g.beginPath(); g.fillStyle = `hsla(${(h[0] + i * 37) % 360} 80% 62% / .6)`; g.arc(50 + i * 70, 220 + 110 * Math.sin(i + n), 36 + 12 * (i % 3), 0, 7); g.fill() }
  g.fillStyle = 'rgba(255,255,255,.9)'; g.font = 'bold 30px sans-serif'; g.fillText('Школа №45 · стена ' + (n + 1), 26, 448)
  return c.toDataURL('image/jpeg', .85)
}, n)
// МОП: «Сделки» → № 1710 → шаг «Закрытие»
async function closeStep(p) {
  await tab(p, 'Сделки')
  await p.locator('.chips.scroll button', { hasText: 'Все' }).click()
  await p.locator('.stage .qrow', { hasText: '№ 1710' }).click()
  await p.locator('.hero .steps').waitFor()
  await p.locator('.hero .steps > div', { hasText: 'Закрытие' }).click()
  const c = p.locator('.closepanel')
  await c.locator('.cklist').waitFor()
  return c
}

;(async () => {
  const b = await chromium.launch()
  const VALS = JSON.parse(execSync(`cd ${BE} && ${PY} -c "import sys,json;sys.path+=['tests'];from test_finance import VALS;print(json.dumps(VALS))"`).toString())
  await call(1000, '/register', { full_name: 'Раман' })
  await e2e('/consts', { ...VALS, vat: 16, 'pay.trip_food': 3000, 'fin.margin.model': 70 })
  const people = {}
  for (const [tg, name, role, zones, extra] of [[6000, 'Ануар', 'mop', ['sales'], { bitrix_user_id: 4565 }], [3000, 'Ерлан', 'lead_artist', ['mural'], {}],
    [2000, 'Ажар', 'artist', ['mural'], {}]]) {
    people[tg] = (await call(tg, '/register', { full_name: name })).id
    await call(1000, `/people/${people[tg]}`, { role_code: role, zones, ...extra })
  }
  // Сделка 1710 в «Выполнении проекта»: договор, КП и счёт есть, АВР ещё нет; аванс 50% внесён и сверен
  await e2e('/deal/1710', { TITLE: '1710 · ШКОЛА №45 — АСТАНА', STAGE_ID: 'UC_AV00QK', OPPORTUNITY: '1160000.00', ASSIGNED_BY_ID: '4565', MYCOMPANY_ID: '1103',
    COMPANY_ID: '77', DATE_MODIFY: new Date().toISOString(), UF_CRM_6881101914D8D: '12077', UF_CRM_ARTGAME_AREA_M2: '120', UF_CRM_1753294730602: '19285',
    UF_CRM_1755520919823: 'ул. Достык 5|51.1;71.4|1947', UF_CRM_ARTGAME_NORM_SHIFTS: '3', UF_CRM_ARTGAME_TERM_DAYS: '5',
    UF_CRM_ARTGAME_PROJECT_START_ACTUAL: day(-6) + 'T03:00:00+03:00', UF_CRM_ARTGAME_PROJECT_END_PLAN: day(-3) + 'T03:00:00+03:00',
    UF_CRM_1753202415: FILE, UF_CRM_1753202391: FILE, UF_CRM_ARTGAME_DOC05_INVOICES: FILE })
  psql(`INSERT INTO objects (id, title, city, bitrix_stage, gip_person_id, drive_folder, design_synced_at, area_m2, address)
        VALUES (1710, 'ШКОЛА №45', 'Астана', 'UC_AV00QK', ${people[3000]}, 'deal-1710', now(), 120, 'ул. Достык 5')`)
  await call(6000, '/bx/deals/1710/payment', { client_uid: uid(), amount: 580000, op_date: day(-7), account: 'kaspi', receipt: CHEK, note: 'аванс 50%' })
  const checkAll = async () => { for (const x of await call(1000, '/fin/payments/check')) await call(1000, `/fin/ledger/${x.id}/check`, {}) }
  await checkAll()
  // Смены: Ажар — три, ГИП — одна; всё, кроме последней, утверждено. Докупка краски с чеком. Фото с объекта.
  const shift = (tg, d, a, z) => call(tg, '/shifts', { client_uid: uid(), object_id: 1710, zone_code: 'mural', started_at: `${d}T${a}:00+05:00`, ended_at: `${d}T${z}:00+05:00` })
  const s1 = await shift(2000, day(-5), '09:00', '19:00'), s2 = await shift(2000, day(-4), '09:00', '19:00')
  const s3 = await shift(3000, day(-4), '10:00', '18:00'), s4 = await shift(2000, day(-2), '09:00', '19:00')
  for (const s of [s1, s2]) await call(1000, `/shift/${s.id}/review`, { approve: true })
  await call(1000, `/shift/${s3.id}/review`, { approve: true, stars: 5 })   // смены Главного — со звёздами HEAD (12.11)
  const ex = await call(2000, '/expenses', { client_uid: uid(), object_id: 1710, zone_code: 'mural', category: 'purchase', amount: 45000, receipt: CHEK, note: 'краска, 2 ведра' })
  await call(1000, `/expense/${ex.id}/review`, { approve: true })

  // ГИП: «Проекты» → карточка → «Сдача объекта»: «Работы сданы» вчера
  const g = await open(b, 3000)
  for (let i = 0; i < 4; i++) await call(2000, '/objects/1710/photos', { client_uid: uid(), data: await art(g, i) })
  await tab(g, 'Проекты')
  await g.locator('.pcard', { hasText: '№ 1710' }).click()
  const box = g.locator('.card', { has: g.locator('h3', { hasText: 'Сдача объекта' }) })
  await box.waitFor()
  assert.strictEqual(await box.locator('input[type=date]').inputValue(), day(-2), 'по умолчанию — день последней смены')
  await box.locator('input[type=date]').fill(day(-1))
  await box.getByRole('button', { name: 'Работы сданы' }).click()
  await box.locator('b', { hasText: dmy(day(-1)) }).waitFor()
  assert.match(await box.textContent(), /отметил Ерлан/)
  await box.scrollIntoViewIfNeeded(); await fits(g, 'сдача объекта у ГИП')
  await shot(g, 'close-gip-done')
  assert.strictEqual((await req(2000, '/objects/1710/done', { day: day(-1) })).status, 403, 'художник сдачу не отмечает')

  // Продакшн: ГИП загрузил видео с объекта («Продакшн» → «Загрузить») — ждёт «Утверждаю» HEAD (файл на фейковом Диске — от фото с объекта)
  const vid = psql(`INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by, status, media_type, review)
                    SELECT gen_random_uuid(), 1710, 'media', 'Процесс школа.mp4', 'video/mp4', 9000000, drive_id, ${people[3000]}, 'ready', 'video', 'pending'
                    FROM files WHERE object_id=1710 AND kind='photo' ORDER BY id LIMIT 1 RETURNING id`)
  // МОП переводит на «Оплата+закрывающие документы»: «На закрытие» закрыт — долг, АВР, Продакшн не утверждён, смена на проверке
  await e2e('/deal/1710', { STAGE_ID: 'UC_BMKDS4' })
  psql("UPDATE objects SET bitrix_stage='UC_BMKDS4' WHERE id=1710")
  const p = await open(b, 6000)
  let c = await closeStep(p)
  assert.strictEqual(await p.locator('.hero .steps > div').count(), 7)
  assert.match(await p.locator('.nextstep').textContent(), /Следующий шагЗакрытие.*На закрытие/)
  assert.match(await c.locator('.panelhead .badge').textContent(), /^8 из 12$/)
  assert.deepStrictEqual(await c.locator('.lockbox .miss').allTextContents(), ['Долг 0', 'АВР', 'Продакшн', 'Смены'])
  assert.deepStrictEqual(await c.locator('.ck.bad b').allTextContents(), ['Долг 0: поступило = сумме сделки', 'Подписанный акт (АВР)',
    'Продакшн: фото или видео, утверждённые HEAD', 'Ни одной открытой или непроверенной смены'], 'сверху — что не выполнено')
  assert.match(await c.locator('.ck', { hasText: 'Продакшн:' }).textContent(), /ждут HEAD: 1«Продакшн» → «Загрузить» фото или видео с объекта, HEAD — «Утверждаю» · ГИП или Главный дизайнер$/)
  assert.strictEqual(await c.getByRole('button', { name: 'На закрытие' }).count(), 0, 'пока не всё — кнопки нет')
  assert.match(await c.locator('.ck', { hasText: 'Долг 0' }).textContent(), /долг 580\s000\s₸шаг «Оплата»/)
  assert.strictEqual(await c.locator('.cklist').getByRole('button', { name: 'Выполнено: 8 · показать' }).count(), 1)
  assert.strictEqual(await c.locator('input[type=date]').count(), 0, 'дата сдачи есть — второй раз не спрашиваем')
  assert.ok(!(await c.textContent()).match(/Прибыль|маржа/i), 'МОП прибыль и маржу не видит')
  await fits(p, 'шаг «Закрытие» у МОП')
  await p.locator('.hero .steps').scrollIntoViewIfNeeded(); await shot(p, 'close-mop-card')
  await shot(p, 'close-mop-blocked', c)
  await c.locator('.cklist .ckmore').click()
  assert.match(await c.locator('.ck', { hasText: 'Окончание работ' }).textContent(), new RegExp(dmy(day(-1)) + ' · отметил Ерлан'))
  assert.ok(await c.locator('.ck.skip', { hasText: 'Утверждённый дизайн' }).count(), 'дизайна не было — пункт не нужен')
  await shot(p, 'close-mop-blocked-all', c)
  // «Оплата получена» в списке стадий нет — только через «Закрытие»; сервер тоже не пускает
  await act(p, 'Стадия')
  const opts = await p.locator('.sheetbox select option').evaluateAll(o => o.map(x => x.value))
  assert.ok(opts.includes('UC_BMKDS4') && !opts.includes('WON'), opts.join(','))
  await p.locator('.sheetbox', { hasText: '«Оплата получена» — через шаг «Закрытие»' }).waitFor()
  await p.keyboard.press('Escape'); await p.locator('.sheet').first().click({ position: { x: 5, y: 5 } }).catch(() => {})
  const won = await req(6000, '/bx/deals/1710/stage', { stage: 'WON' })
  assert.strictEqual(won.status, 409); assert.match(won.body.detail, /«На закрытие»/)
  assert.strictEqual((await req(6000, '/bx/deals/1710/close', {})).status, 409, 'с невыполненными пунктами заявку не отправить')

  // доплата сверена, АВР в сделке, смена утверждена, HEAD утвердил видео в Продакшн → все 12 пунктов, «На закрытие»
  await call(1000, `/media/${vid}/review`, { approve: true })
  await call(6000, '/bx/deals/1710/payment', { client_uid: uid(), amount: 580000, op_date: day(0), account: 'kaspi', receipt: CHEK, note: 'остаток' })
  await checkAll()
  await call(1000, `/shift/${s4.id}/review`, { approve: true })
  await e2e('/deal/1710', { UF_CRM_ARTGAME_DOC05_ACTS: FILE })
  await p.reload()
  c = await closeStep(p)
  assert.match(await c.locator('.panelhead .badge').textContent(), /^12 из 12$/)
  assert.strictEqual(await c.locator('.lockbox').count(), 0)
  assert.strictEqual(await c.locator('.ck').count(), 0); await c.getByRole('button', { name: 'Все 12 пунктов выполнены · показать' }).waitFor()
  await fits(p, 'всё готово')
  await shot(p, 'close-mop-ready', c)
  await c.getByRole('button', { name: 'На закрытие' }).click()
  await p.locator('.toast', { hasText: 'Заявка ушла HEAD' }).waitFor()
  await c.locator('.hint', { hasText: 'На закрытии у HEAD с ' + dmy(day(0)) }).waitFor()
  await c.locator('.panelhead .badge', { hasText: 'у HEAD' }).waitFor()
  await shot(p, 'close-mop-sent', c)
  let bot = []   // бот шлёт фоном после ответа — ждём до 5 с
  for (let i = 0; i < 25 && !bot.length; i++) { bot = (await e2e('/sent')).filter(x => x.tg === 1000 && /На закрытие: № 1710/.test(x.text || '')); if (!bot.length) await p.waitForTimeout(200) }
  assert.strictEqual(bot.length, 1, 'HEAD — уведомление в бот')
  assert.match(bot[0].text, /^🔒 На закрытие: № 1710 · ШКОЛА №45 — АСТАНА\n1 160 000 ₸ · МОП Ануар Минкеев\n/)
  assert.ok(!/прибыл|марж/i.test(bot[0].text), 'в боте без прибыли и маржи')

  // Сделка 1720 закрыта прямо в Битриксе мимо паспорта — красным на Пульте
  await e2e('/deal/1720', { TITLE: '1720 · КАФЕ ЛАТТЕ — АСТАНА', STAGE_ID: 'WON', OPPORTUNITY: '450000.00', ASSIGNED_BY_ID: '4565', MYCOMPANY_ID: '1103',
    MOVED_TIME: new Date().toISOString(), MOVED_BY_ID: '4565', DATE_MODIFY: new Date().toISOString(), UF_CRM_1753202391: FILE })

  // HEAD: Пульт → «Сделки на закрытие» → паспорт сделки
  const h = await open(b, 1000)
  const ask = h.locator('.qrow', { hasText: 'Сделки на закрытие: 1' })
  await ask.waitFor()
  assert.match(await ask.textContent(), /№ 1710 · 1\s160\s000\s₸ · паспорт сделки/)
  const by = h.locator('.qrow', { hasText: 'Закрыты мимо вас в Битриксе: 1' })
  assert.match(await by.locator('.why').textContent(), /№ 1720 · принять или вернуть/)
  assert.ok(await h.locator('.qrow.hot', { hasText: 'Закрыты мимо вас' }).count(), 'закрытая мимо паспорта — красным')
  assert.ok(!(await h.locator('.pulse-kpi button').first().getAttribute('class')).includes('hot'), '«0 на проверке» не красным')
  await fits(h, 'Пульт HEAD')
  await shot(h, 'close-head-pulse')
  await ask.click()
  await h.locator('h2', { hasText: 'Закрытие сделок' }).waitFor()
  await h.locator('.card', { hasText: 'Ждут решения · 1' }).locator('.qrow', { hasText: '№ 1710' }).waitFor()
  await h.locator('.card.bypass .qrow', { hasText: '№ 1720' }).waitFor()
  await fits(h, 'вкладка «Закрытие»')
  await shot(h, 'close-head-list')
  await h.locator('.qrow', { hasText: '№ 1710' }).click()
  const hero = h.locator('.passhero')
  await hero.waitFor()
  const nums = await hero.locator('.passnums').textContent()
  // без НДС 1 000 000; ФОТ: Ажар 3 смены по 10 ч, Ерлан 1 смена; докупка 45 000
  assert.match(nums, /Выручка без НДС1\s000\s000\s₸/)
  assert.match(nums, /Маржа\d+(,\d)?%норма 70%/)
  const flags = await h.locator('.card.flags').textContent()
  assert.match(flags, new RegExp(`Срок сорван: сдали ${dmy(day(-1))}, по плану ${dmy(day(-3))} \\(\\+2 дн\\.\\)`))
  assert.match(flags, /Затраты выше расчёта: смен 4 при расчёте 3/)
  assert.ok(!flags.includes('Не выполнено'), 'пункты — в «Пунктах закрытия», не во флагах')
  await h.locator('.card', { has: h.locator('h3', { hasText: 'Пункты закрытия' }) }).getByRole('button', { name: 'Все 12 пунктов выполнены · показать' }).waitFor()
  assert.match(await h.locator('.card.decide').textContent(), new RegExp('На закрытие отправил Ануар · ' + dmy(day(0))))
  const fot = h.locator('.cgroup', { hasText: 'ФОТ' })
  await fot.locator('.row').click()
  assert.match(await fot.textContent(), /Ажар.*Художник · 3 смены · 30 ч.*Ерлан.*1 смена · 8 ч/)
  const mat = h.locator('.cgroup', { hasText: 'Материалы' })
  await mat.locator('.row').click()
  await mat.locator('a', { hasText: 'Чеки и записи · 1' }).click()
  assert.match(await mat.textContent(), /Докупка.*Ажар.*45\s000\s₸чек/)
  assert.deepStrictEqual(await h.locator('.docchips .tag').allTextContents(), ['КП · 1', 'Договор подписанный · 1', 'Счета · 1', 'АВР · 1', 'Прочие документы · нет', 'Эскиз · нет'])
  assert.strictEqual(await h.locator('.passph .ph').count(), 4)
  await h.locator('.passph .ph').first().getByRole('button', { name: 'В Продакшн' }).click()
  await h.locator('.passph .ph').first().locator('.badge', { hasText: 'в Продакшн' }).waitFor()
  await fits(h, 'паспорт сделки')
  await shot(h, 'close-head-passport', null, true)
  await h.evaluate(() => window.scrollTo(0, 0)); await shot(h, 'close-head-passport-top')

  // «Вернуть»: пункт + причина → МОП и ГИП в чате «HEAD», стадия та же
  await h.locator('.card.decide').getByRole('button', { name: 'Вернуть' }).click()
  const sh = h.locator('.sheetbox')
  await sh.locator('textarea').fill('Нет фото фасада со стороны входа')
  await sh.locator('.chips button', { hasText: 'Фото объекта' }).click()
  await fits(h, 'окно «Вернуть»')
  await h.waitForTimeout(300); await shot(h, 'close-head-return')
  await sh.getByRole('button', { name: 'Вернуть МОП и ГИП' }).click()
  await h.locator('.toast', { hasText: 'Вернули на доработку: сообщение ушло МОП и ГИП (2)' }).waitFor()
  assert.strictEqual(psql("SELECT count(*) FROM dm WHERE from_head AND text LIKE '%возвращена с закрытия%Нет фото фасада%'"), '2')
  assert.ok(!(await e2e('/bx_calls')).some(x => x.params.id === 1710 && x.method === 'crm.deal.update' && x.params.fields.STAGE_ID), 'стадию не трогали')

  // МОП видит, что вернули и почему; доделал — снова «На закрытие»
  await p.reload()
  c = await closeStep(p)
  const lb = c.locator('.lockbox', { hasText: 'HEAD вернул' })
  await lb.waitFor()
  assert.match(await lb.textContent(), /Нет фото фасада со стороны входа.*Фото объекта/)
  await fits(p, 'возврат у МОП')
  await shot(p, 'close-mop-returned', c)
  await call(2000, '/objects/1710/photos', { client_uid: uid(), data: await art(p, 3) })
  await c.getByRole('button', { name: 'На закрытие' }).click()
  await p.locator('.toast', { hasText: 'Заявка ушла HEAD' }).waitFor()

  // HEAD «Закрыть»: «Оплата получена» и «Окончание факт» в Битрикс, без денег в ленте; паспорт снимком, PDF в «ДОКУМЕНТЫ»
  await h.reload()
  await h.locator('.qrow', { hasText: 'Сделки на закрытие: 1' }).click()
  await h.locator('.card', { hasText: 'Ждут решения · 1' }).locator('.qrow', { hasText: '№ 1710' }).click()
  await h.locator('.card.decide').getByRole('button', { name: 'Закрыть', exact: true }).click()
  await h.locator('.toast', { hasText: 'Сделка закрыта: «Оплата получена», паспорт сохранён' }).waitFor()
  const closed = h.locator('.card', { has: h.locator('h3', { hasText: 'Закрытые' }) })
  assert.match(await closed.locator('.qrow', { hasText: '№ 1710' }).textContent(), /1\s160\s000\s₸ · \d\d\.\d\d\.\d{4} · маржа \d+/)
  assert.match(await h.locator('.card', { hasText: 'Ждут решения' }).first().textContent(), /Ждут решения · 0/)
  await shot(h, 'close-head-closed-list')
  const calls = (await e2e('/bx_calls')).filter(x => x.params.id === 1710 || x.params.fields?.ENTITY_ID === 1710)
  const upd = calls.filter(x => x.method === 'crm.deal.update' && x.params.fields.STAGE_ID)
  assert.deepStrictEqual(upd.map(x => x.params.fields), [{ STAGE_ID: 'WON', UF_CRM_ARTGAME_PROJECT_END_ACTUAL: day(-1) }])
  const note = calls.filter(x => x.method === 'crm.timeline.comment.add').map(x => x.params.fields.COMMENT).join(' ')
  assert.ok(/паспорт сделки/.test(note) && !/₸|прибыл|марж/i.test(note), 'в ленту Битрикса — без денег: ' + note)
  await closed.locator('.qrow', { hasText: '№ 1710' }).click()
  await h.locator('.passhero .tag.okt', { hasText: 'закрыта ' + dmy(day(0)) + ' · Раман' }).waitFor()
  const pdf = h.locator('a', { hasText: 'PDF паспорта в «ДОКУМЕНТЫ»' })
  await pdf.waitFor({ timeout: 5000 }).catch(async () => { await h.reload(); await tab(h, 'Закрытие'); await closed.locator('.qrow', { hasText: '№ 1710' }).click(); await pdf.waitFor() })
  assert.match(await pdf.getAttribute('href'), /^https:\/\/drive\.google\.com\/file\/d\/drv\d+\/view$/)
  assert.strictEqual(await h.locator('.card.decide').count(), 0, 'закрытую не закрыть второй раз')
  await fits(h, 'закрытая сделка')
  await shot(h, 'close-head-frozen')

  // закрытый объект: ни смены, ни расхода задним числом; МОП (и ГИП) — сообщение в «Чат» → «HEAD»; закрытой сделки в списке больше нет
  const late = await req(2000, '/shifts', { client_uid: uid(), object_id: 1710, zone_code: 'mural', started_at: `${day(-1)}T09:00:00+05:00`, ended_at: `${day(-1)}T12:00:00+05:00` })
  assert.strictEqual(late.status, 400); assert.match(late.body.detail, /закрыта HEAD/)
  assert.strictEqual((await req(2000, '/expenses', { client_uid: uid(), object_id: 1710, zone_code: 'mural', category: 'purchase', amount: 1000, receipt: CHEK })).status, 400)
  await p.reload()
  await tab(p, 'Чат')
  await p.locator('.dmhq').click()
  await p.locator('.dmb', { hasText: '✅ Сделка № 1710 «ШКОЛА №45 — АСТАНА» закрыта. Паспорт сохранён' }).waitFor()
  await p.locator('.dmb', { hasText: '↩️ Сделка № 1710 «ШКОЛА №45 — АСТАНА» возвращена с закрытия' }).waitFor()
  await fits(p, 'чат МОП')
  await shot(p, 'close-mop-chat')

  // как на test: нормы маржи в «Значениях» нет — маржа без сравнения, без пометки и без строки о ней
  await e2e('/consts', { ...VALS, vat: 16, 'pay.trip_food': 3000 })
  // закрытая мимо паспорта: HEAD видит красным; пункты не выполнены — принять нельзя, только вернуть на «Оплата+закрывающие» (HEAD 12.11)
  await h.locator('a.back').click()
  await h.locator('.card.bypass .qrow', { hasText: '№ 1720' }).click()
  await h.locator('.passhero .tag.hott', { hasText: 'закрыта в Битриксе мимо паспорта' }).waitFor()
  assert.ok(!/норм|модел/i.test(await h.locator('.passhero').textContent()), 'без нормы маржи — ни сравнения, ни пояснения')
  const dc = h.locator('.card.decide')
  await dc.locator('.lockbox').waitFor()
  assert.match(await dc.locator('.lockbox').textContent(), /^🔒 «Принять закрытие» откроется, когда будут выполнены все пунктыНе выполнено \d+ из 12:.*Долг 0.*Фото объекта.*Продакшн/)
  assert.strictEqual(await dc.getByRole('button', { name: /Принять|Закрыть/ }).count(), 0, 'без всех пунктов кнопки закрытия нет')
  const force = await req(1000, '/head/closing/1720/close', {})
  assert.strictEqual(force.status, 409, 'сервер тоже не закрывает'); assert.match(force.body.detail, /только когда выполнены все пункты\. Не выполнено: Долг 0/)
  await fits(h, 'закрытая мимо паспорта')
  await shot(h, 'close-head-bypass')
  await dc.getByRole('button', { name: 'Вернуть на «Оплата+закрывающие»' }).click()
  const rs = h.locator('.sheetbox')
  assert.ok((await rs.locator('.chips button.on').allTextContents()).includes('Долг 0'), 'невыполненные пункты отмечены сами')
  await rs.getByRole('button', { name: 'Вернуть МОП и ГИП' }).click()
  await h.locator('.toast', { hasText: 'Вернули на доработку' }).waitFor()
  assert.deepStrictEqual((await e2e('/bx_calls')).filter(x => x.params.id === 1720 && x.method === 'crm.deal.update').map(x => x.params.fields),
    [{ STAGE_ID: 'UC_BMKDS4' }], 'вернули — сделка назад на «Оплата+закрывающие»')
  await h.locator('.card.bypass').waitFor({ state: 'detached' })
  assert.strictEqual(psql("SELECT count(*) FROM deal_close WHERE deal_id=1720 AND status='closed'"), '0')

  // старая сделка на «Оплата+закрывающие» без фото и сдачи: HEAD открыл паспорт из карточки — «Закрыть» нет, замок со списком
  await e2e('/deal/1730', { TITLE: '1730 · ОФИС КАСПИЙ — АЛМАТЫ', STAGE_ID: 'UC_BMKDS4', OPPORTUNITY: '300000.00', ASSIGNED_BY_ID: '4565', MYCOMPANY_ID: '1103',
    DATE_MODIFY: new Date().toISOString(), UF_CRM_1753202415: FILE, UF_CRM_1753202391: FILE, UF_CRM_ARTGAME_DOC05_INVOICES: FILE })
  await tab(h, 'Сделки')
  await h.locator('.chips.scroll button', { hasText: 'Все' }).click()
  await h.locator('.stage .qrow', { hasText: '№ 1730' }).click()
  await h.locator('.hero .steps > div', { hasText: 'Закрытие' }).click()
  await h.locator('.closepanel .cklist').waitFor()
  await h.locator('.closepanel').getByRole('button', { name: 'Паспорт сделки', exact: true }).click()
  await dc.locator('.lockbox').waitFor()
  assert.match(await dc.locator('.lockbox').textContent(), /^🔒 «Закрыть» откроется, когда будут выполнены все пунктыНе выполнено \d+ из 12:.*Окончание работ \(факт\).*Фото объекта.*Продакшн/)
  assert.strictEqual(await dc.getByRole('button', { name: /Закрыть/ }).count(), 0, '«Закрыть всё равно» нет')
  await dc.getByRole('button', { name: 'Вернуть', exact: true }).waitFor()
  assert.strictEqual((await req(1000, '/head/closing/1730/close', {})).status, 409)
  await fits(h, 'паспорт без всех пунктов')
  await h.evaluate(() => document.querySelector('.passhero').scrollIntoView({ block: 'start' }))
  await shot(h, 'close-head-locked')
  assert.ok(!(await e2e('/bx_calls')).some(x => x.params.id === 1730), 'в Битрикс ничего не ушло')

  await b.close()
  console.log('zakrytie OK')
})().catch(e => { console.error(e); process.exit(1) })

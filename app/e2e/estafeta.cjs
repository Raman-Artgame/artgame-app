// Сквозной тест «Эстафета сделки» (HEAD 26.11 «отлично, давай так сделаем»): МОП «Нужен дизайн» → дизайнер загружает эскиз
// и жмёт «Утверждено» (эскиз получает метку «В работу») → у МОП в «Сегодня» строка «передай в производство», в карточке
// полоска пути → «В производство»: стадия, сроки и куратор ГИП одной кнопкой → ГИП видит проект с утверждённым эскизом первым.
// API — e2e/fake_api.py (Битрикс подменён); экран — vite preview :4173.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const raw = async (path, body) => (await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })).json()
const bxCalls = async () => (await fetch(API + '/_e2e/bx_calls')).json()
const shots = process.env.SHOTS || '/var/tmp'

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.route('https://fonts.googleapis.com/**', r => r.fulfill({ body: '', contentType: 'text/css' }))
  await p.route('https://upload.example/**', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'drvBIG00000301' }) }))
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
const fits = async (p, what) => assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), `${what}: ничего не уезжает вбок`)
async function deal(p, id) {
  await tab(p, 'Сделки')
  await p.locator('.card input[placeholder^="Номер"]').fill(`${id}`)
  await p.locator('.kc', { hasText: `№ ${id}` }).first().click()
  await p.locator('.hero .dpath').waitFor()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const ids = {}
  for (const [tg, name, role, zones, bxu] of [[6000, 'Ануар', 'mop', ['sales'], 4565], [7100, 'Малика', 'designer_asst', ['design'], 4693],
    [6100, 'Айдана', 'lead_artist', ['mural'], null], [6200, 'Тимур', 'print_master', ['print'], null]]) {
    ids[tg] = (await call(tg, '/register', { full_name: name })).id
    await call(1000, `/people/${ids[tg]}`, { role_code: role, zones, ...(bxu ? { bitrix_user_id: bxu } : {}) })
  }
  // сделка 1601: договор отправлен, аванс пришёл
  await raw('/_e2e/deal/1601', { STAGE_ID: 'FINAL_INVOICE' })
  const pay0 = await call(6000, '/bx/deals/1601/payment', { client_uid: '7c1d2e3f-4a5b-4c6d-8e7f-901234567890', amount: 300000,
    op_date: new Date().toISOString().slice(0, 10), account: 'cash', receipt: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==' })
  assert.ok(pay0.ok || pay0.row, 'аванс внесён: ' + JSON.stringify(pay0).slice(0, 200))

  // 1. МОП просит дизайн; дизайнер грузит эскиз в карточке и жмёт «Утверждено»
  const t = await call(6000, '/bx/deals/1601/design-tasks', { title: 'Холл, стена у входа', deadline: '2027-01-20' })
  assert.ok(t.id, 'задача на дизайн поставлена')
  const d = await open(b, 7100)
  await tab(d, 'Дизайн')
  await d.locator('.dtstage .dtrow', { hasText: 'Холл' }).click()
  await d.locator('.sheetbox').getByRole('button', { name: 'Беру в работу' }).click()
  await d.waitForFunction(() => document.querySelector('.sheetbox select')?.value === 'work')
  await d.locator('.sheetbox label.photo input[type=file]').setInputFiles({ name: 'Холл вариант 3@100x.png', mimeType: 'image/png', buffer: Buffer.from('PNG-DATA') })
  await d.locator('.sheetbox .mitem', { hasText: 'Холл вариант 3' }).waitFor()
  await d.locator('.sheetbox').getByRole('button', { name: 'Утверждено' }).click()
  await d.locator('.dtstage.done .dtrow', { hasText: 'Холл' }).waitFor()

  // 2. МОП: «Сегодня» — строка «эскиз утверждён — передай в производство»
  const m = await open(b, 6000)
  await m.locator('.qrow', { hasText: 'передай в производство' }).waitFor()
  assert.match(await m.locator('.qrow', { hasText: 'передай в производство' }).textContent(), /№ 1601/)
  await m.screenshot({ path: `${shots}/est-1-mop-segodnya.png` })
  // карточка: полоска пути — «Дизайн» и «Утверждён» зелёные, сейчас «Производство»
  await deal(m, 1601)
  assert.deepStrictEqual(await m.locator('.hero .dpbar .dp').evaluateAll(a => a.map(x => x.className.replace('dp ', ''))), ['done', 'done', 'now', 'todo', 'todo'])
  await m.screenshot({ path: `${shots}/est-1b-mop-sdelka.png` })
  await m.locator('.hero .steps > div', { hasText: 'Оплата' }).click()
  const pay = m.locator('.card', { has: m.locator('h3', { hasText: /^Оплата$/ }) })
  assert.strictEqual(await pay.getByRole('button', { name: 'Передать куратору ГИП' }).count(), 0, 'старой кнопки-заметки нет')
  await pay.getByRole('button', { name: 'В производство' }).click()
  await m.locator('.sheetbox .prodsk', { hasText: 'Холл вариант 3' }).waitFor()
  await m.locator('.sheetbox select').first().selectOption({ label: 'Айдана · Главный художник' })
  // второй куратор ГИП (HEAD 28.11): появляется после выбора первого, первого в списке нет
  await m.locator('.sheetbox select.gip2').selectOption({ label: 'Тимур · Мастер настенной печати' })
  assert.strictEqual(await m.locator('.sheetbox select.gip2 option', { hasText: 'Айдана' }).count(), 0)
  await m.waitForTimeout(400)
  await fits(m, 'окно «В производство»')
  await m.screenshot({ path: `${shots}/est-2-mop-v-proizvodstvo.png` })
  // у МОП карточка заполнена не до конца — замок показывает, чего не хватает, и кнопка не нажимается
  assert.ok(await m.locator('.sheetbox .lockbox').count(), 'замок карточки')
  assert.ok(await m.locator('.sheetbox button', { hasText: /^Передать/ }).isDisabled())

  // 3. HEAD (замок карточки на него не действует) передаёт в производство той же кнопкой
  const h = await open(b, 1000)
  await deal(h, 1601)
  await h.locator('.hero .steps > div', { hasText: 'Оплата' }).click()
  await h.locator('.card', { has: h.locator('h3', { hasText: /^Оплата$/ }) }).getByRole('button', { name: 'В производство' }).click()
  await h.locator('.sheetbox select').first().selectOption({ label: 'Айдана · Главный художник' })
  await h.locator('.sheetbox select.gip2').selectOption({ label: 'Тимур · Мастер настенной печати' })
  const before = (await bxCalls()).length
  await h.locator('.sheetbox button', { hasText: /^Передать/ }).click()
  await h.locator('.sheetbox').waitFor({ state: 'detached' })
  const w = (await bxCalls()).slice(before)
  const upd = w.find(x => x.method === 'crm.deal.update')
  assert.strictEqual(upd.params.fields.STAGE_ID, 'UC_AV00QK', 'стадия «Выполнение проекта»')
  assert.ok(w.some(x => x.method === 'crm.timeline.comment.add' && /куратор ГИП Айдана.*Холл вариант 3/.test(JSON.stringify(x))), 'заметка в ленту сделки')

  // 3б. МОП: «Сделки» → доска «В работе» (HEAD 26.11): на карточке оплачено/долг, куратор ГИП, срок сдачи
  await m.reload()
  await tab(m, 'Сделки')
  await m.getByRole('button', { name: 'Обновить' }).click()
  await m.locator('.segf button', { hasText: 'В работе' }).click()
  const wc = m.locator('.kc', { hasText: '№ 1601' })   // телефон — стадии кнопками, карточки во всю ширину (HEAD 26.11)
  await wc.waitFor()
  console.log('work card:', await wc.textContent())
  assert.match(await wc.locator('.kmeta').textContent(), /ГИП Айдана, Тимур.*сдача \d\d\.\d\d/)
  await wc.locator('.kpay').waitFor()
  assert.strictEqual(await wc.getAttribute('draggable'), 'false', 'на доске «В работе» стадии не тянут')
  await fits(m, 'доска «В работе»')
  await m.screenshot({ path: `${shots}/est-2b-mop-v-rabote.png` })
  await m.setViewportSize({ width: 1440, height: 900 }); await m.waitForTimeout(400)
  await m.screenshot({ path: `${shots}/est-2b-mop-v-rabote-wide.png` })
  await m.setViewportSize({ width: 390, height: 844 })

  // 4. ГИП: «Проекты» → проект с полоской пути и утверждённым эскизом первым; ГИП может ставить людей
  const g = await open(b, 6100)
  await tab(g, 'Проекты')
  await g.locator('.pcard', { hasText: '1601' }).click()
  await g.locator('.dpath').waitFor()
  assert.deepStrictEqual(await g.locator('.dpbar .dp').evaluateAll(a => a.map(x => x.className.replace('dp ', ''))), ['done', 'done', 'done', 'now', 'todo'])
  assert.ok((await call(6100, '/objects/1601/crew')).can_edit, 'ГИП ставит людей на объект')
  await fits(g, 'проект у ГИП')
  await g.screenshot({ path: `${shots}/est-3-gip-proekt.png` })
  // второй куратор ГИП: те же права — видит проект, ставит людей; HEAD в карточке проекта видит обоих
  assert.ok((await call(6200, '/objects/1601/crew')).can_edit, 'второй куратор ставит людей на объект')
  await tab(h, 'Проекты')
  await h.locator('.pcard', { hasText: '1601' }).click()
  await h.locator('.gippick select.gip2').scrollIntoViewIfNeeded()
  await h.locator('.gippick select.gip2:not([disabled])').waitFor()
  assert.strictEqual(await h.locator('.gippick select.gip2').evaluate(e => e.selectedOptions[0].textContent), 'Тимур · Мастер настенной печати')
  await fits(h, 'два куратора в проекте')
  await h.screenshot({ path: `${shots}/gip2-proekt.png` })
  await b.close()
  console.log('OK: дизайн утверждён файлом → «Сегодня» МОП → «В производство» (стадия + ГИП + сроки) → ГИП видит проект и эскиз')
})().catch(e => { console.error('FAIL', e.message); process.exit(1) })

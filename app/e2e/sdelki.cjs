// Сквозной тест блока МОП v2 (HEAD 05.11): «Сегодня» очередью, «Лиды», сделки воронкой, карточка шагами, итог звонка,
// запись в Битрикс, КП и «Документы». API — e2e/fake_api.py (Битрикс подменён ответами tests/test_bx.py); экран — vite preview :4173.
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
// Меню: до пяти кнопок, остальное в листе «Ещё» (HEAD 05.11)
async function tab(p, name) {
  const nav = p.locator('nav')
  const re = new RegExp(`^${name}\\s*\\d*$`)   // у кнопки может быть счётчик: «Лиды1»
  if (await nav.getByRole('button', { name: re }).count()) return nav.getByRole('button', { name: re }).click()
  await nav.locator('button').last().click()   // «Ещё» (или имя открытой оттуда вкладки)
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}
async function dealsOpen(p) {
  await tab(p, 'Сделки')
  await p.locator('.chips.scroll').waitFor()
  await p.locator('.chips.scroll button', { hasText: 'Все' }).click()
  await p.locator('.stagehead').first().waitFor()
}
async function card(p, id) {
  await dealsOpen(p)
  await p.locator('.stage .qrow', { hasText: `№ ${id}` }).click()
  await p.locator('.steps').waitFor()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  await fetch(API + '/_e2e/consts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ vat: '16',
    'pay.mop.salary': '200000', 'pay.mop.bonus_plan': '100000', 'pay.mop.step1.from': '2000000', 'pay.mop.step1.pct': '3',
    'pay.mop.step2.from': '7000000', 'pay.mop.step2.pct': '4', 'pay.mop.step3.from': '15000000', 'pay.mop.step3.pct': '5' }) })
  const m = await call(6000, '/register', { full_name: 'Ануар', phone: '+7 701 111 22 33' })
  await call(1000, `/people/${m.id}`, { role_code: 'mop', zones: ['sales'] })

  // HEAD: связывает МОП с пользователем Битрикса во вкладке «Команда», видит все сделки
  const h = await open(b, 1000)
  await tab(h, 'Команда')
  await h.locator('.person', { hasText: 'Ануар' }).locator('label select').selectOption({ label: 'Ануар Минкеев' })
  await h.waitForTimeout(500)
  assert.strictEqual((await call(1000, '/people')).find(x => x.id === m.id).bitrix_user_id, 4565)
  await dealsOpen(h)
  assert.strictEqual(await h.locator('.stage .qrow').count(), 2, 'HEAD видит все открытые сделки')

  // МОП: «Сегодня» — очередь: лид, где клиентка ждёт ответа в WhatsApp, горит; КП без ответа — сегодня; полоска месяца сверху
  const p = await open(b, 6000)
  await p.locator('.bucket.hot').waitFor()
  assert.match(await p.locator('.bucket.hot').textContent(), /Дана.*клиент ждёт ответа в WhatsApp 2 ч/)
  // сколько в «Сегодня» и «Можно позже» — зависит от даты прогона (сделки фикстуры стареют), проверяем согласованность
  const tiles = (await p.locator('.tiles').textContent()).match(/^1Горит(\d+)Сегодня(\d+)Можно позже/)
  assert.ok(tiles, 'плитки: 1 горит, затем сегодня и позже')
  assert.match(await p.locator('nav button', { hasText: 'Сегодня' }).textContent(), new RegExp(`${1 + +tiles[1]}$`), 'счётчик в меню')
  assert.strictEqual(await p.locator('nav button').count(), 5, 'у МОП пять кнопок меню')
  assert.match(await p.locator('.bucket.today').textContent(), /№ 1601.*КП без ответа/)
  assert.strictEqual(await p.locator('.bucket.hot a.btn', { hasText: 'Ответить' }).getAttribute('href'), 'https://fake.bitrix24.kz/crm/lead/details/3001/', '«Ответить» ведёт в карточку Битрикса (Wazzup там)')
  await p.locator('.strip').waitFor()
  assert.match(await p.locator('.strip').textContent(), /Месяц: 2,5 млн из 7 млн.*до 4% ещё 4,5 млн/)
  await p.screenshot({ path: `${shots}/mop-today.png`, fullPage: true })

  // Сделки воронкой: только свои, стадия с количеством и суммой, бейдж дней
  await dealsOpen(p)
  assert.strictEqual(await p.locator('.stage .qrow').count(), 1)
  assert.match(await p.locator('.stagehead').first().textContent(), /Встреча\/Отправка КП.*1.*589\s250/)
  assert.match(await p.locator('.stage .qrow').first().textContent(), /1601.*КАФЕ.*дн\./)
  await p.screenshot({ path: `${shots}/mop-deals.png` })

  // Карточка: шаги, контакт, расчёт
  await p.locator('.stage .qrow').first().click()
  await p.locator('.steps').waitFor()
  assert.match(await p.locator('.nextstep').textContent(), /Следующий шаг.*Договор.*Договор и счёт/)   // площадь есть, КП на стадии «Отправка КП»
  assert.match(await p.locator('.steps').textContent(), /Клиент.*Расчёт.*КП.*Договор.*Оплата/)
  assert.match(await p.locator('.contact').textContent(), /Ромашка.*\+77001112233/)
  assert.strictEqual(await p.locator('.contact a.btn', { hasText: 'В Битриксе' }).getAttribute('href'), 'https://fake.bitrix24.kz/crm/deal/details/1601/')
  assert.strictEqual(await p.locator('.contact .alt').count(), 0)   // HEAD 05.11: связь только через карточку Битрикса
  await p.locator('.segf').getByRole('button', { name: 'Срок и деньги' }).click()
  await p.getByRole('button', { name: 'Срок и состав' }).click()
  await p.locator('.dealedit input[type=number]').fill('60')
  await p.getByRole('button', { name: 'Посчитать и записать в сделку' }).click()
  await p.locator('text=По норме: 6 смен, 3 чел., 4 раб. дн.').waitFor()
  await p.locator('.kv', { hasText: 'Смен по норме' }).waitFor()
  // «Цена клиенту» → калькулятор рабочего места с площадью и сложностью сделки (HEAD 06.11: отдельного «Калькулятора» больше нет)
  await p.getByRole('button', { name: 'Цена клиенту' }).click()
  await p.waitForFunction(() => (document.querySelector('iframe.placeframe')?.contentWindow?.location.hash || '') === '#calc', null, { timeout: 20000 })
  await p.waitForFunction(() => document.querySelector('iframe.placeframe')?.contentDocument?.getElementById('p-m2')?.value === '60', null, { timeout: 20000 })
  assert.strictEqual(await p.locator('.place .chips button', { hasText: 'Калькулятор' }).count(), 0)
  // «Клиентам»: без окна «Поделиться» (как на компьютере) главная кнопка — «Скачать»; с ним — «Отправить» и маленькая «↓»
  await mopFrame(p).evaluate(() => { location.hash = '#mat' })
  await mopFrame(p).locator('.matb').first().waitFor()
  assert.match(await mopFrame(p).locator('.matb').first().textContent(), /Скачать$/)
  const shctx = await b.newContext({ viewport: { width: 390, height: 800 } })
  await shctx.addInitScript(() => { navigator.share = () => Promise.resolve(); navigator.canShare = () => true })
  const sp = await shctx.newPage()
  await sp.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, sign(6000))
  await sp.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await sp.goto('http://127.0.0.1:4173/')
  await sp.locator('nav button', { hasText: 'Место' }).waitFor()
  await tab(sp, 'Место')
  await sp.locator('iframe.placeframe').waitFor()
  await sp.waitForFunction(() => !!document.querySelector('iframe.placeframe')?.contentDocument?.querySelector('#app'), null, { timeout: 20000 })
  await mopFrame(sp).evaluate(() => { location.hash = '#mat' })
  await mopFrame(sp).locator('.matb').first().waitFor()
  assert.match(await mopFrame(sp).locator('.matb').first().textContent(), /Отправить↓$/)
  await mopFrame(sp).locator('.matb button[data-s]').first().click()
  await mopFrame(sp).locator('#matst', { hasText: 'Отправлено.' }).waitFor()
  await sp.screenshot({ path: `${shots}/mop-mat-share.png` })
  await shctx.close()
  await card(p, 1601)
  // итог звонка с перезвоном → комментарий и задача
  await p.locator('.segf').getByRole('button', { name: 'Действия' }).click()
  await p.getByRole('button', { name: 'Итог звонка' }).click()
  await p.locator('.dealedit').getByRole('button', { name: 'Перезвонить' }).click()
  await p.locator('.dealedit input[placeholder="О чём договорились"]').fill('ждёт эскиз')
  await p.locator('.dealedit').getByRole('button', { name: 'Записать' }).click()
  await p.locator('text=Записано в Битрикс, задача поставлена.').waitFor()
  await p.screenshot({ path: `${shots}/mop-card.png`, fullPage: true })
  // заметка и «Отложено» с датой — из карточки
  await p.locator('.wrapbtns').getByRole('button', { name: 'Заметка' }).click()
  await p.locator('.dealedit input').fill('Клиент просил перезвонить в четверг')
  await p.locator('.dealedit').getByRole('button', { name: 'Записать' }).click()
  await p.locator('text=Записано в Битрикс.').waitFor()
  await p.locator('.wrapbtns').getByRole('button', { name: 'Стадия' }).click()
  await p.locator('.dealedit select').selectOption('UC_VCP4VO')
  assert.ok(await p.getByRole('button', { name: 'Перевести' }).isDisabled())   // только с датой возврата
  const until = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10)
  await p.locator('.dealedit input[type=date]').fill(until)
  await p.locator('.dealedit input[placeholder="Почему отложили"]').fill('ждут бюджет')
  await p.getByRole('button', { name: 'Перевести' }).click()
  await p.locator('.card .tag', { hasText: 'Отложено' }).waitFor()
  let calls = await bxCalls()
  assert.ok(calls.some(c => c.method === 'crm.timeline.comment.add' && /Ануар \(приложение\): просил перезвонить: ждёт эскиз/.test(c.params.fields.COMMENT)))
  assert.ok(calls.some(c => c.method === 'crm.timeline.comment.add' && /Клиент просил перезвонить в четверг/.test(c.params.fields.COMMENT)))
  assert.ok(calls.some(c => c.method === 'crm.deal.update' && c.params.fields.STAGE_ID === 'UC_VCP4VO'))
  assert.ok(calls.some(c => c.method === 'tasks.task.add' && c.params.fields.DEADLINE.startsWith(until)))

  // «Документы» и «КП» из карточки: страница сама подтягивает сделку
  await p.locator('.wrapbtns').getByRole('button', { name: 'Документы' }).click()
  await p.waitForFunction(() => /заполнено/.test(document.querySelector('iframe.placeframe')?.contentDocument?.querySelector('#app .agbx-st')?.textContent || ''), null, { timeout: 20000 })
  const ds = await mopFrame(p).evaluate(() => ({ num: DS.num, cname: DS.cname, ctel: DS.ctel }))
  assert.deepStrictEqual(ds, { num: '1601', cname: 'ТОО «Ромашка»', ctel: '+77001112233' })
  const n0 = (await bxCalls()).length
  await mopFrame(p).evaluate(() => { DS.total = 600000; DS.area = 25; DS.adv = 50; dsSave(); return window.ARTGAME_ON_DOWNLOAD({ name: 'ARTGAME_Dogovor_1601.docx', fid: 'nofile' }) })
  await p.waitForFunction(n => fetch('/api/_e2e/bx_calls').then(r => r.json()).then(c => c.length > n), n0)
  const upd = (await bxCalls()).slice(n0).find(c => c.method === 'crm.deal.update')
  assert.strictEqual(upd.params.fields.OPPORTUNITY, 600000)
  await card(p, 1601)
  await p.locator('.wrapbtns').getByRole('button', { name: 'КП' }).click()
  await p.waitForFunction(() => /загружена/.test(document.querySelector('iframe.placeframe')?.contentDocument?.getElementById('crmStatus')?.textContent || ''), null, { timeout: 20000 })
  assert.strictEqual(await mopFrame(p).evaluate(() => document.getElementById('client').value), 'ТОО «Ромашка»')

  // «Месяц»
  await tab(p, 'Месяц')
  await p.locator('h3', { hasText: 'Мои закрытые сделки' }).waitFor()
  // План месяца: 2,5 млн без НДС → ступень 1 (3%), до ступени 2 ещё 4,5 млн, заработок 200 000 + 75 000, отметки 2/7/15 млн
  const plan = p.locator('.plan')
  assert.match(await plan.locator('.planhead').textContent(), /2,5 млн.*ступень 1, 3%/)
  assert.strictEqual(await plan.locator('.tick').count(), 3)
  assert.strictEqual(await plan.locator('.tick.got').count(), 1)
  assert.match(await plan.textContent(), /До ступени 2 \(4%\) — ещё 4\s500\s000/)
  assert.match(await p.locator('.kv').first().textContent(), /Заработок сейчас275\s000.*Мой вклад2\s500\s000.*100%/)
  await p.screenshot({ path: `${shots}/mop-plan.png` })
  assert.match(await p.locator('.card', { hasText: 'Мои закрытые сделки' }).textContent(), /1590/)
  // Траты отдела продаж: лимит не задан → трата с чеком уходит HEAD; без чека кнопка закрыта
  const spend = p.locator('.card', { hasText: 'Мои траты' })
  await spend.waitFor()
  assert.match(await spend.textContent(), /Лимит на месяц ещё не задан/)
  await spend.getByRole('button', { name: '+ Трата' }).click()
  await spend.locator('.chips button', { hasText: 'Выезды и транспорт' }).click()
  await spend.locator('input[placeholder="Сумма, ₸"]').fill('3500')
  await spend.locator('input[placeholder^="На что"]').fill('такси на замер')
  await spend.locator('input[placeholder^="№ сделки"]').fill('1601')
  assert.ok(await spend.getByRole('button', { name: 'Записать трату' }).isDisabled(), 'без фото чека не записать')
  const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
  await spend.locator('input[type=file]').setInputFiles({ name: 'chek.png', mimeType: 'image/png', buffer: PNG })
  await spend.locator('.photo img').waitFor()
  await spend.getByRole('button', { name: 'Записать трату' }).click()
  await p.locator('text=Трата ушла на одобрение HEAD.').waitFor()
  await spend.locator('.row', { hasText: '3 500' }).waitFor()
  assert.match(await spend.locator('.row', { hasText: '3 500' }).textContent(), /Выезды и транспорт.*такси на замер.*сделка № 1601.*ждёт HEAD/)
  await p.screenshot({ path: `${shots}/mop-spend.png`, fullPage: true })

  // Лиды: список с недостающими полями → карточка → город и площадь → «В сделку» → карточка новой сделки
  await tab(p, 'Лиды')
  await p.locator('.qrow', { hasText: 'Дана' }).waitFor()
  assert.match(await p.locator('.segf').textContent(), /Новые.*1.*В работе.*0.*Все.*1/)
  assert.match(await p.locator('.qrow', { hasText: 'Дана' }).textContent(), /нет: город.*нет: площадь/)
  await p.screenshot({ path: `${shots}/mop-leads.png` })
  await p.locator('.qrow', { hasText: 'Дана' }).click()
  await p.locator('h3', { hasText: 'Что нужно для сделки' }).waitFor()
  assert.ok(await p.getByRole('button', { name: 'В сделку' }).isDisabled())
  await p.locator('input[list=lead-cities]').fill('Астана')
  await p.locator('label', { hasText: 'Площадь' }).locator('input').fill('40')
  await p.getByRole('button', { name: 'Сохранить в Битрикс' }).click()
  await p.locator('text=Всё заполнено, можно в сделку.').waitFor()
  await p.screenshot({ path: `${shots}/mop-lead.png`, fullPage: true })
  await p.getByRole('button', { name: 'В сделку' }).click()
  await p.locator('h2', { hasText: '№ 9100' }).waitFor()
  calls = await bxCalls()
  const add = calls.find(c => c.method === 'crm.deal.add')
  assert.strictEqual(add.params.fields.UF_CRM_6881101914D8D, '12077')
  assert.strictEqual(add.params.fields.LEAD_ID, 3001)
  assert.ok(calls.some(c => c.method === 'crm.lead.update' && c.params.fields.STATUS_ID === 'CONVERTED'))

  // HEAD: «Журнал» со сводкой по МОП (у МОП этой вкладки нет)
  assert.strictEqual(await p.locator('nav').getByRole('button', { name: 'Журнал' }).count(), 0)
  assert.strictEqual(await p.locator('nav').getByRole('button', { name: 'Ещё' }).count(), 0)
  // HEAD: трата сверх лимита — во «Проверке», понятная строка вместо «Офис / без объекта»
  await tab(h, 'Проверка')
  await h.locator('.row', { hasText: 'Отдел продаж · Выезды и транспорт · сделка № 1601 · сверх лимита' }).waitFor()
  await tab(h, 'Журнал')   // у HEAD — через «Ещё»
  await h.locator('.row', { hasText: 'Ануар' }).first().waitFor()
  // Вход с компьютера без Telegram: телефон → код от бота → приложение; «Выйти» возвращает на вход
  const wctx = await b.newContext({ viewport: { width: 1280, height: 800 } })
  const w = await wctx.newPage()
  await w.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await w.goto('http://127.0.0.1:4173/')
  await w.locator('input[placeholder^="+7"]').fill('8 701 111 22 33')
  await w.getByRole('button', { name: 'Получить код' }).click()
  await w.locator('text=код уже в Telegram').waitFor()
  const code = (await (await fetch(API + '/_e2e/sent')).json()).filter(x => x.tg === 6000).pop().text.match(/\d{6}/)[0]
  await w.locator('input[placeholder="Код из Telegram"]').fill(code)
  await w.screenshot({ path: `${shots}/web-login.png` })
  await w.getByRole('button', { name: 'Войти' }).click()
  await w.locator('.webbar', { hasText: 'Ануар' }).waitFor()
  await w.locator('.tiles').waitFor()
  await w.screenshot({ path: `${shots}/web-today.png` })
  await w.reload()
  await w.locator('.webbar').waitFor()   // вход помнится
  await w.getByRole('button', { name: 'Выйти' }).click()
  await w.getByRole('button', { name: 'Получить код' }).waitFor()
  console.log('OK: «Сегодня» очередью, лиды → сделка, воронка, карточка шагами, итог звонка, запись в Битрикс, КП и «Документы», месяц с планом, вход с компьютера')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

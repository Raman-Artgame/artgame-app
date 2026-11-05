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
const tab = (p, name) => p.locator('nav').getByRole('button', { name, exact: true }).click()
async function dealsOpen(p) {
  await tab(p, 'Сделки')
  await p.locator('.stagehead').first().waitFor()
  for (const h of await p.locator('.stagehead').all()) if ((await h.textContent()).includes('▸')) await h.click()
}
async function card(p, id) {
  await dealsOpen(p)
  await p.locator('.stage .qrow', { hasText: `№ ${id}` }).click()
  await p.locator('.steps').waitFor()
}

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  const m = await call(6000, '/register', { full_name: 'Ануар' })
  await call(1000, `/people/${m.id}`, { role_code: 'mop', zones: ['sales'] })

  // HEAD: связывает МОП с пользователем Битрикса во вкладке «Команда», видит все сделки
  const h = await open(b, 1000)
  await tab(h, 'Команда')
  await h.locator('.person', { hasText: 'Ануар' }).locator('label select').selectOption({ label: 'Ануар Минкеев' })
  await h.waitForTimeout(500)
  assert.strictEqual((await call(1000, '/people')).find(x => x.id === m.id).bitrix_user_id, 4565)
  await dealsOpen(h)
  assert.strictEqual(await h.locator('.stage .qrow').count(), 2, 'HEAD видит все открытые сделки')

  // МОП: «Сегодня» — очередь: новый лид горит, КП без ответа — сегодня; полоска месяца сверху
  const p = await open(b, 6000)
  await p.locator('.bucket.hot').waitFor()
  assert.match(await p.locator('.bucket.hot').textContent(), /лид.*№ 3001.*Дана.*новый лид без ответа/)
  assert.match(await p.locator('.bucket.today').textContent(), /№ 1601.*КП без ответа/)
  assert.ok(await p.locator('.bucket.hot a.btn', { hasText: 'Позвонить' }).count() >= 1, 'у лида с телефоном — кнопка «Позвонить»')
  await p.locator('.strip').waitFor()
  assert.match(await p.locator('.strip').textContent(), /Месяц: 2,9 млн/)
  await p.screenshot({ path: `${shots}/mop-today.png`, fullPage: true })

  // Сделки воронкой: только свои, стадия с количеством и суммой, бейдж дней
  await dealsOpen(p)
  assert.strictEqual(await p.locator('.stage .qrow').count(), 1)
  assert.match(await p.locator('.stagehead').first().textContent(), /Встреча\/Отправка КП.*1.*589\s250/)
  assert.match(await p.locator('.stage .qrow').first().textContent(), /1601.*КАФЕ.*дн\./)
  await p.screenshot({ path: `${shots}/mop-deals.png` })

  // Карточка: шаги, контакт, расчёт
  await p.locator('.bucket.today, .stage .qrow').first().click()
  await p.locator('.steps').waitFor()
  assert.match(await p.locator('.steps').textContent(), /Клиент.*Расчёт.*КП.*Договор.*Оплата/)
  assert.match(await p.locator('.contact').textContent(), /Ромашка.*\+77001112233/)
  assert.strictEqual(await p.locator('.contact a.btn', { hasText: 'WhatsApp' }).getAttribute('href'), 'https://wa.me/77001112233')
  await p.getByRole('button', { name: 'Сделать расчёт' }).click()
  await p.locator('.dealedit input[type=number]').fill('60')
  await p.getByRole('button', { name: 'Посчитать и записать в сделку' }).click()
  await p.locator('text=По норме: 6 смен, 3 чел., 4 раб. дн.').waitFor()
  await p.locator('.kv', { hasText: 'Смен по норме' }).waitFor()
  // итог звонка с перезвоном → комментарий и задача
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
  assert.match(await p.locator('.card', { hasText: 'Мои закрытые сделки' }).textContent(), /1590/)

  // Лиды: список с недостающими полями → карточка → город и площадь → «В сделку» → карточка новой сделки
  await tab(p, 'Лиды')
  await p.locator('.qrow', { hasText: 'Дана' }).waitFor()
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
  await tab(h, 'Журнал')
  await h.locator('.row', { hasText: 'Ануар' }).first().waitFor()
  console.log('OK: «Сегодня» очередью, лиды → сделка, воронка, карточка шагами, итог звонка, запись в Битрикс, КП и «Документы», месяц')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

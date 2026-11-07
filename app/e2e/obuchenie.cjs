// Обучающее видео для МОП (HEAD 06.11): проход по приложению на фейковом Битриксе (fake_api.py) с подписями. OUT=папка для .webm; склейка — ffmpeg.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const fs = require('fs')
const BE = __dirname + '/../backend'
const OUT = process.env.OUT
const sign = id => execSync(`cd ${BE} && python3 -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const VP = { width: 390, height: 780 }

const OVERLAY = () => {
  const css = `#tcap{position:fixed;left:0;right:0;top:0;z-index:2147483647;background:#0B0B0D;color:#F1F0EC;font:600 15px/1.35 Onest,system-ui,sans-serif;
    padding:12px 16px;min-height:86px;display:flex;flex-direction:column;justify-content:center;gap:2px;box-shadow:0 2px 12px rgba(0,0,0,.25)}
    #tcap b{color:#FF3D6E;font-size:12px;letter-spacing:.08em;text-transform:uppercase;font-weight:700}
    html body{padding-top:86px !important} #tcap{pointer-events:none} .sheetbox{max-height:calc(100dvh - 100px) !important}
    .tdot{position:fixed;z-index:2147483646;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;border:3px solid #E60041;background:rgba(230,0,65,.18);pointer-events:none;animation:tdot .7s ease-out forwards}
    @keyframes tdot{from{transform:scale(.4);opacity:1}to{transform:scale(1.4);opacity:0}}`
  const put = () => {
    if (!document.body || document.getElementById('tcap')) return
    const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s)
    const d = document.createElement('div'); d.id = 'tcap'; d.innerHTML = window.__tcap || ''; document.body.appendChild(d)
  }
  document.addEventListener('DOMContentLoaded', put); setInterval(put, 300)
  document.addEventListener('pointerdown', e => { const d = document.createElement('div'); d.className = 'tdot'; d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; document.body.appendChild(d); setTimeout(() => d.remove(), 800) }, true)
}

async function open(b, id, dir) {
  const ctx = await b.newContext({ viewport: VP, recordVideo: { dir, size: VP } })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.addInitScript(OVERLAY)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.goto('http://127.0.0.1:4173/')
  return { p, ctx }
}
const W = (p, ms) => p.waitForTimeout(ms)
async function cap(p, head, text, ms) {
  const h = `<b>${head}</b><span>${text}</span>`
  await p.evaluate(h => { window.__tcap = h; const d = document.getElementById('tcap'); if (d) d.innerHTML = h }, h)
  await W(p, ms || Math.max(3200, text.length * 55))
}
async function tab(p, name) {
  const nav = p.locator('nav')
  const re = new RegExp(`^${name}\\s*\\d*$`)
  if (await nav.getByRole('button', { name: re }).count()) return nav.getByRole('button', { name: re }).click()
  await nav.locator('button').last().click(); await W(p, 900)
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}
const step = (p, name) => p.locator('.hero .steps > div', { hasText: name }).click()
const scroll = async (p, y, ms = 1400) => { await p.evaluate(y => window.scrollTo({ top: y, behavior: 'smooth' }), y); await W(p, ms) }
const mopFrame = p => p.frames().find(f => f.url().includes('/api/p/mop/'))

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'HEAD' })
  await fetch(API + '/_e2e/consts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ vat: '16',
    'pay.mop.salary': '200000', 'pay.mop.bonus_plan': '100000', 'pay.mop.step1.from': '2000000', 'pay.mop.step1.pct': '3',
    'pay.mop.step2.from': '7000000', 'pay.mop.step2.pct': '4', 'pay.mop.step3.from': '15000000', 'pay.mop.step3.pct': '5' }) })

  // 1. Регистрация (отдельная запись)
  const r = await open(b, 6100, OUT + '/a')
  await r.p.locator('input').first().waitFor()
  await cap(r.p, 'Шаг 1 · Вход', 'Откройте бота ARTGAME в Telegram и нажмите кнопку меню — откроется приложение.', 3500)
  await r.p.locator('input').first().fill('')
  await r.p.locator('input').first().pressSequentially('Тимур', { delay: 70 })
  await r.p.locator('input').nth(1).pressSequentially('+7 701 000 00 00', { delay: 50 })
  await cap(r.p, 'Шаг 1 · Вход', 'Впишите имя и свой рабочий телефон и нажмите «Отправить».', 3000)
  await r.p.getByRole('button', { name: 'Отправить' }).click()
  await r.p.getByText('Заявка у HEAD').waitFor()
  await cap(r.p, 'Шаг 1 · Вход', 'Заявка ушла HEAD. Он назначит роль МОП и свяжет вас с Битриксом — после этого откроются ваши лиды и сделки.', 5000)
  await r.ctx.close()

  // МОП, уже с ролью и Битриксом
  const m = await call(6000, '/register', { full_name: 'Ануар', phone: '+7 701 111 22 33' })
  await call(1000, `/people/${m.id}`, { role_code: 'mop', zones: ['sales'] })
  await call(1000, `/people/${m.id}`, { bitrix_user_id: 4565 })
  const { p, ctx } = await open(b, 6000, OUT + '/b'); global.P = p
  await p.locator('.bucket.hot').waitFor()
  await cap(p, 'Шаг 2 · Сегодня', 'Каждый день начинайте отсюда. Это ваша очередь из Битрикса на сегодня.', 3500)
  await cap(p, 'Шаг 2 · Сегодня', '«Горит» — клиент ждёт ответа или пропущен звонок. Сначала их. «Ответить» открывает чат в Битриксе.', 5000)
  await scroll(p, 420)
  await cap(p, 'Шаг 2 · Сегодня', '«Сегодня» — КП без ответа и задачи. «Можно позже» — то, что не горит. Внизу — ваш месяц и сколько до следующего процента.', 5500)
  await scroll(p, 0, 800)

  // Лиды
  await tab(p, 'Лиды')
  await p.locator('.qrow', { hasText: 'Дана' }).waitFor()
  await cap(p, 'Шаг 3 · Лиды', 'Новые заявки. Красным видно, чего не хватает, чтобы сделать из лида сделку.', 4200)
  await p.locator('.qrow', { hasText: 'Дана' }).click()
  await p.locator('h3', { hasText: 'Обязательно для сделки' }).waitFor()
  await cap(p, 'Шаг 3 · Лиды', 'Звонок и WhatsApp — только через кнопку Битрикса. С личного номера не пишем. После звонка — «Итог звонка».', 5000)
  await p.locator('h3', { hasText: 'Обязательно для сделки' }).scrollIntoViewIfNeeded(); await W(p, 800)
  await cap(p, 'Шаг 3 · Лиды', 'Узнайте у клиента город, услугу и площадь и впишите сюда. Без них кнопка «В сделку» не откроется.', 4500)
  await p.locator('input[list=lead-cities]').pressSequentially('Астана', { delay: 80 }); await W(p, 500)
  await p.locator('label', { hasText: 'Площадь' }).locator('input').pressSequentially('40', { delay: 120 })
  await p.getByRole('button', { name: 'Сохранить в Битрикс' }).click()
  await p.locator('.miss', { hasText: 'услуга' }).waitFor(); await W(p, 800)
  await p.locator('label', { hasText: 'Услуга' }).locator('select').selectOption({ label: 'Художественная роспись стен' })
  await p.locator('text=Всё заполнено, можно в сделку.').waitFor()
  await cap(p, 'Шаг 3 · Лиды', 'Всё заполнено — жмите «В сделку». Клиент и сделка создадутся в Битриксе сами.', 4000)
  await p.getByRole('button', { name: 'В сделку' }).scrollIntoViewIfNeeded(); await W(p, 600)
  await p.getByRole('button', { name: 'В сделку' }).click()
  await p.locator('.hero h2', { hasText: '№ 9100' }).waitFor()
  await cap(p, 'Шаг 3 · Лиды', 'Готово: открылась карточка новой сделки.', 3200)

  // Сделка 1601
  await tab(p, 'Сделки')
  await p.locator('.stage .qrow').first().waitFor()
  await cap(p, 'Шаг 4 · Сделки', 'Ваши сделки по стадиям воронки. Видите только свои.', 3500)
  await p.locator('.stage .qrow', { hasText: '1601' }).first().click()
  await p.locator('.hero .steps').waitFor()
  await cap(p, 'Шаг 4 · Карточка сделки', 'Сверху шаги: Клиент → Расчёт → КП → Договор → Оплата → В работе. Красная кнопка ведёт к следующему шагу.', 5500)
  await cap(p, 'Шаг 4 · Карточка сделки', 'Тёмная полоса «Обязательно заполнить» — чего не хватает. Пока не заполнено, дальше сделка не пойдёт.', 5000)
  // Расчёт
  const calc = p.locator('.card', { has: p.locator('h3', { hasText: 'Расчёт' }) })
  await calc.scrollIntoViewIfNeeded()
  await cap(p, 'Шаг 5 · Расчёт', 'Площадь подтянулась из сделки. Поменяйте, если клиент назвал другую, выберите сложность и надбавки.', 4500)
  await calc.locator('input[type=number]').first().fill('')
  await calc.locator('input[type=number]').first().pressSequentially('60', { delay: 150 })
  await calc.locator('.total b', { hasText: '1 191 000' }).waitFor(); await W(p, 800)
  await calc.locator('.chips button', { hasText: 'Лак' }).click()
  await calc.locator('.total b', { hasText: '1 310 000' }).waitFor()
  await calc.locator('.two').scrollIntoViewIfNeeded()
  await cap(p, 'Шаг 5 · Расчёт', 'Цена, аванс, смены и срок для клиента считаются сами — по ценам из «Значений». Ничего не считаем вручную.', 5000)
  await calc.getByRole('button', { name: 'Записать в сделку' }).scrollIntoViewIfNeeded()
  await calc.getByRole('button', { name: 'Записать в сделку' }).click()
  await p.locator('.nextstep', { hasText: 'Договор' }).waitFor()
  await cap(p, 'Шаг 5 · Расчёт', '«Записать в сделку» — сумма, площадь и срок ушли в Битрикс.', 3500)
  await scroll(p, 0, 900)
  // Замок
  await step(p, 'Договор')
  await p.locator('.lockbox').waitFor(); await p.locator('.lockbox').scrollIntoViewIfNeeded()
  await cap(p, 'Шаг 6 · Замок', 'Договор закрыт: в сделке ещё нет КП. Так приложение не даёт пропустить шаг.', 4500)
  await scroll(p, 0, 900)
  // Помощник
  await p.locator('.hero').getByRole('button', { name: 'Заполнить карточку' }).click()
  await p.locator('.sheetbox textarea').waitFor()
  await cap(p, 'Шаг 7 · Заполнить карточку', 'Сюда можно вставить переписку из WhatsApp или анкету клиента.', 3800)
  await p.locator('.sheetbox textarea').fill('Здравствуйте! Нужна роспись в кафе, Астана, ул. Достык 5, примерно 60 м². Аванс 50%, срок 20 дней. ТОО «Ромашка», БИН 123456789012')
  await W(p, 900)
  await p.locator('.sheetbox').getByRole('button', { name: 'Разобрать' }).click()
  await p.locator('.sheetbox p.small', { hasText: 'подставлено' }).waitFor()
  await cap(p, 'Шаг 7 · Заполнить карточку', 'Поля заполнились сами — они жёлтые с меткой «ИИ». Проверьте и нажмите «Записать в Битрикс».', 5000)
  await p.locator('.sheetbox').evaluate(e => { const s = e.querySelector('.sheetbody') || e; s.scrollTo({ top: 600, behavior: 'smooth' }) }); await W(p, 2200)
  await p.locator('.sheetbox .x').click(); await W(p, 700)
  // КП
  await step(p, 'КП')
  await p.waitForFunction(() => document.querySelector('.embed iframe')?.contentWindow?.KPGEN?.count() === 1, null, { timeout: 30000 })
  await p.locator('.embed').scrollIntoViewIfNeeded()
  await cap(p, 'Шаг 8 · КП', 'КП собирается само: клиент, сделка и позиция из расчёта уже внутри. Проверьте и скачайте PDF.', 5000)
  await scroll(p, 1400, 1800)
  await cap(p, 'Шаг 8 · КП', 'Скачанный КП сам ложится в сделку Битрикса, стадия меняется на «Отправка КП». Файл отправьте клиенту из Битрикса.', 5500)
  const dl = execSync('python3 -c "import tempfile;print(tempfile.gettempdir())"').toString().trim() + '/artgame-dl'
  fs.mkdirSync(dl, { recursive: true }); fs.writeFileSync(dl + '/tourkp.bin', '%PDF-1.4 tour')
  await mopFrame(p).evaluate(() => window.ARTGAME_ON_DOWNLOAD({ name: 'КП 1601 Ромашка.pdf', fid: 'tourkp' }))
  await W(p, 2500)
  // Договор
  await scroll(p, 0, 900)
  await step(p, 'Договор')
  await p.waitForFunction(() => /заполнено/.test(document.querySelector('.embed iframe')?.contentDocument?.querySelector('#app .agbx-st')?.textContent || ''), null, { timeout: 30000 })
  await p.locator('.embed').scrollIntoViewIfNeeded()
  await cap(p, 'Шаг 9 · Договор и счёт', 'КП в сделке — договор открылся. Сумма и аванс из расчёта, реквизиты из Битрикса или из вставленной анкеты.', 5500)
  await scroll(p, 1300, 1800)
  await cap(p, 'Шаг 9 · Договор и счёт', 'Скачали договор или счёт — файл в сделке, стадия сменилась сама.', 4000)
  await scroll(p, 0, 900)
  // Итог звонка
  await p.locator('.hero').getByRole('button', { name: 'Итог звонка' }).click()
  await p.locator('.sheetbox').getByRole('button', { name: 'Перезвонить' }).waitFor()
  await cap(p, 'Шаг 10 · Итог звонка', 'После каждого разговора — «Итог звонка». Если надо перезвонить, укажите о чём договорились: бот напомнит, в Битриксе появится задача.', 5500)
  await p.locator('.sheetbox').getByRole('button', { name: 'Перезвонить' }).click()
  await p.locator('.sheetbox input[placeholder="О чём договорились"]').pressSequentially('ждёт эскиз', { delay: 70 })
  await p.locator('.sheetbox').getByRole('button', { name: 'Записать' }).click()
  await p.locator('.toast', { hasText: 'Итог звонка записан.' }).waitFor()
  await W(p, 1500)
  // Стадия под замком
  await p.locator('.hero').getByRole('button', { name: 'Стадия' }).click()
  await p.locator('.sheetbox select').selectOption('UC_AV00QK')
  await p.locator('.sheetbox .lockbox').waitFor(); await W(p, 600)
  await cap(p, 'Шаг 11 · Стадия', 'Стадию можно сменить вручную, но вперёд — только когда всё нужное заполнено. Замок покажет, чего не хватает.', 5500)
  await p.locator('.sheetbox select').selectOption('LOSE'); await W(p, 900)
  await cap(p, 'Шаг 11 · Отказ', 'Отказ — только с одной из 8 причин и комментарием, что сказал клиент. «Отложено» — только с датой, когда вернуться.', 5500)
  await p.locator('.sheetbox .x').click(); await W(p, 700)
  // Проекты, Месяц, Учёба
  await tab(p, 'Проекты')
  await p.locator('.proj').first().waitFor()
  await cap(p, 'Шаг 12 · Проекты', 'Все объекты в работе: старт, сдача, сколько дней осталось. Удобно ответить клиенту, когда сможем начать.', 5000)
  await tab(p, 'Месяц')
  await p.locator('h3', { hasText: 'Мои закрытые сделки' }).waitFor()
  await cap(p, 'Шаг 13 · Месяц', 'Выручка месяца против плана 2 / 7 / 15 млн, ваш процент и заработок сейчас и по темпу.', 5000)
  const spend = p.locator('.card', { hasText: 'Мои траты' })
  await spend.scrollIntoViewIfNeeded()
  await cap(p, 'Шаг 13 · Месяц', 'Траты на работу (такси на замер и т. п.) — сюда, обязательно с фото чека. Каждую одобряет HEAD.', 5000)
  await tab(p, 'Учёба')
  await W(p, 3500)
  await cap(p, 'Шаг 14 · Учёба', 'В «Ещё» → «Учёба»: учебник, тест и правила игры. Пройдите тест в первый день.', 4500)
  await tab(p, 'Сегодня')
  await p.locator('.bucket').first().waitFor()
  await cap(p, 'Главное', 'Всё, что вы делаете в приложении, само уходит в Битрикс. Не заполнено — дальше не пойдёт. Вопросы — к HEAD.', 6000)
  await ctx.close()
  await b.close()
})().catch(async e => { console.error(e); try { await global.P.screenshot({ path: OUT + '/fail.png' }) } catch (x) {} process.exit(1) })

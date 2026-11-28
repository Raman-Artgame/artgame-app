// Сквозной тест «Смены и расходы»: API на тестовой базе + vite preview.
// Запуск: см. app/README.md (API — e2e/fake_api.py, Диск подменён). Подпись Telegram делается тестовым токеном 123:test-token.
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

async function page(b, id, name, android) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 780 }, ...(android ? { permissions: ['camera'],
    userAgent: 'Mozilla/5.0 (Linux; Android 14; SM-A546B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36 Telegram-Android/11.4.2' } : {}) })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(([d, name]) => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: name } }, ready() {} } } }, [d, name])
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  p.on('dialog', dl => dl.accept('Нет чека'))
  await p.goto('http://127.0.0.1:4173/')
  return { p, ctx }
}

async function tab(p, name) {
  const nav = p.locator('nav')
  const btn = nav.getByRole('button', { name, exact: true })
  if (await btn.waitFor({ timeout: 3000 }).then(() => true, () => false)) return nav.getByRole('button', { name, exact: true }).click()
  await nav.locator('button').last().click()   // «Ещё»
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const b = await chromium.launch({ args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] })   // камера для Android-проверки
  await call(1000, '/register', { full_name: 'HEAD' })
  const lead = await call(3000, '/register', { full_name: 'Главный' })
  await call(1000, `/people/${lead.id}`, { role_code: 'lead_artist', zones: ['mural'] })

  // 1. Художник регистрируется сам и ждёт роли
  const { p: a, ctx } = await page(b, 2000, 'Дана')
  // первый вход — анкета «Мои данные» (HEAD 09.11)
  const an = a.locator('.card.profile')
  await an.getByRole('button', { name: 'Сохранить' }).waitFor()
  await an.locator('input').nth(0).fill('Дана'); await an.locator('input').nth(1).fill('Ахметова')   // 28.11: сначала Имя
  await an.locator('input[type=date]').fill('2000-05-01')
  await an.locator('input[inputmode=tel]').first().fill('+7 701 000 00 01')
  await an.getByRole('button', { name: 'Астана' }).click()
  await a.screenshot({ path: `${shots}/00-registr.png` })
  await an.getByRole('button', { name: 'Сохранить' }).click()
  await a.getByText('Заявка у HEAD').waitFor()
  await a.screenshot({ path: `${shots}/00-zayavka.png` })
  // HEAD назначает роль и зону на вкладке «Команда»
  const { p: h } = await page(b, 1000, 'HEAD')
  await tab(h, 'Команда')
  const row = h.locator('.person', { hasText: 'Дана' })
  await row.getByText('ждёт роли').waitFor()
  await row.locator('select').selectOption('artist')
  // зона роли ставится сама (08.11): «Роспись» уже включена, кликать не нужно
  await h.waitForFunction(() => [...document.querySelectorAll('.person')].find(r => r.textContent.includes('Дана'))
    ?.querySelector('.zones button:not(.ghost)')?.textContent === 'Роспись')
  await h.screenshot({ path: `${shots}/0-komanda.png` })
  await a.reload()

  // 2. Смена по шагам (HEAD 08.11): объект в работе, условия заполнил МОП → фото «до» → «Начать» → м², «что сделал», фото «после»
  const psql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "${q}"`)
  psql("INSERT INTO objects (id, title, city, bitrix_stage, level, area_m2, address, geo, drive_folder) VALUES (731, 'Кафе e2e', 'Астана', 'UC_AV00QK', 'medium', 60, 'Мангилик Ел 1', '51.09;71.41', 'deal-731') ON CONFLICT (id) DO UPDATE SET bitrix_stage='UC_AV00QK', level='medium', geo='51.09;71.41', drive_folder='deal-731'")
  psql(`INSERT INTO deal_calc (deal_id, data) VALUES (731, '{\\"in\\": {\\"service\\": \\"mural\\", \\"level\\": \\"medium\\", \\"extras\\": [\\"height\\"], \\"surface\\": true}}') ON CONFLICT DO NOTHING`)
  await a.reload()
  await a.getByRole('button', { name: 'Начать смену' }).waitFor()
  await a.locator('.promo').getByText('Средний').waitFor()
  assert.ok(await a.getByRole('button', { name: 'Начать смену' }).isDisabled())   // без фото «до» не начать
  // HEAD 17.11: «у Лизы Самсунг, не может сфоткать, только фото добавить» — на Android «Камера» открывает свою камеру в приложении
  {
    const { p: an, ctx: actx } = await page(b, 2000, 'Дана', true)
    await an.getByRole('button', { name: 'Начать смену' }).waitFor()
    await an.locator('.snapbtns button.btnlike', { hasText: 'Камера' }).click()
    const sh = an.locator('.shooter')
    await sh.locator('video').waitFor()
    await an.waitForFunction(() => document.querySelector('.shooter video')?.videoWidth > 0)
    await sh.getByRole('button', { name: 'Снять' }).and(an.locator(':enabled')).waitFor()
    await an.screenshot({ path: `${shots}/1-android-kamera.png` })
    await sh.getByRole('button', { name: 'Снять' }).click()
    await an.locator('.snap img').waitFor()
    assert.equal(await an.locator('.shooter').count(), 0)
    assert.ok(!(await an.getByRole('button', { name: 'Начать смену' }).isDisabled()), 'после снимка камерой смену можно начать')
    await an.screenshot({ path: `${shots}/1-android-snyato.png` })
    await actx.close()
  }
  await a.locator('.snapbtns input[type=file]').last().setInputFiles(__dirname + '/chek.png')
  await a.locator('.snap img').waitFor()
  await a.screenshot({ path: `${shots}/1-smena.png`, fullPage: true })
  await a.getByRole('button', { name: 'Начать смену' }).click()
  await a.getByText('Смена идёт').waitFor()
  await a.locator('input[inputmode=decimal]').fill('12,5')
  await a.locator('textarea').fill('Загрунтовал стену и перенёс эскиз')
  // HEAD 16.11: в конце смены — несколько фото сразу из галереи, и есть кнопка «Камера»
  await a.locator('label.btnlike', { hasText: 'Камера' }).first().waitFor()
  await a.locator('.snapbtns input[type=file]').last().setInputFiles([__dirname + '/chek.png', __dirname + '/chek.png', __dirname + '/chek.png'])
  await a.locator('.pics img').nth(2).waitFor()
  await a.screenshot({ path: `${shots}/1-smena-idet.png`, fullPage: true })
  await a.getByRole('button', { name: 'Закончить и отправить на проверку' }).click()
  await a.getByText('Смена закончена').waitFor()
  for (let i = 0; i < 40; i++) {   // доп. фото ушли очередью после «Закончить»
    const n = +execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -tAc "SELECT count(*) FROM shift_photos"`).toString().trim()
    if (n >= 2) break
    if (i === 39) throw new Error('доп. фото смены не дошли: ' + n)
    await a.waitForTimeout(250)
  }

  // 3. Расход без сети → очередь → сеть вернулась → ушёл
  await a.getByRole('button', { name: 'Расход' }).click()
  await a.locator('input[inputmode=numeric]').fill('15000')
  // HEAD 24.11: без чека и без «на что потрачено» кнопка не нажимается
  assert.ok(await a.getByRole('button', { name: 'Отправить расход' }).isDisabled())
  await a.getByText('Чтобы отправить, нужны: на что потрачено, чек.').waitFor()
  await a.screenshot({ path: `${shots}/rashod-bez-cheka.png`, fullPage: true })
  await a.getByPlaceholder(/Например: краска/).fill('краска белая, 2 ведра')
  await a.locator('.receipt input').first().setInputFiles(__dirname + '/chek.png')   // из галереи (HEAD 10.11)
  await a.locator('.receipt img').waitFor()
  await a.screenshot({ path: `${shots}/rashod-chek.png`, fullPage: true })
  await ctx.setOffline(true)
  await a.getByRole('button', { name: 'Отправить расход' }).click()
  await a.getByText('Сохранено на телефоне').waitFor()
  await ctx.setOffline(false)
  await a.evaluate(() => window.dispatchEvent(new Event('online')))
  await a.waitForTimeout(800)
  await tab(a, 'Кабинет')
  await a.screenshot({ path: `${shots}/2-moi.png` })
  await a.getByText(/15\s000 ₸/).waitFor()
  await a.screenshot({ path: `${shots}/2-moi.png` })

  // 4. HEAD 11.11: Главный художник (куратор) оценивает — 5★ смене, «есть вопрос» расходу; утверждает HEAD
  const { p: l } = await page(b, 3000, 'Главный')
  await tab(l, 'Проверка')
  await l.getByText('Дана').first().waitFor()
  assert.strictEqual(await l.getByRole('button', { name: '✓', exact: true }).count(), 0, 'куратор не утверждает')
  await l.locator('.starpick').first().getByRole('button', { name: '5 из 5' }).click()
  await l.locator('.ratebox textarea').first().fill('Чисто, по эскизу')
  await l.screenshot({ path: `${shots}/3-proverka.png`, fullPage: true })
  // HEAD 18.11: фото отчёта листаются — до, после и доп. фото одной смены, «1 из 4», стрелки и клавиши
  const srow = l.locator('.row', { hasText: 'Загрунтовал стену' }).first()
  await srow.locator('a[href*="/api/files/"] img').first().click()
  const vw = l.locator('.lightbox.viewer')
  await vw.locator('.vcount', { hasText: '1 из 4' }).waitFor()
  await vw.locator('.vbox img').waitFor()
  await l.screenshot({ path: `${shots}/3-listat-1.png` })
  await vw.getByRole('button', { name: 'Дальше' }).click()
  await vw.locator('.vcount', { hasText: '2 из 4' }).waitFor()
  await l.keyboard.press('ArrowLeft'); await l.keyboard.press('ArrowLeft')
  await vw.locator('.vcount', { hasText: '4 из 4' }).waitFor()
  await l.screenshot({ path: `${shots}/3-listat-4.png` })
  // свайп пальцем влево — следующее фото (4 → 1)
  await l.evaluate(() => {
    const el = document.querySelector('.lightbox.viewer')
    const t = x => new Touch({ identifier: 1, target: el, clientX: x, clientY: 400 })
    el.dispatchEvent(new TouchEvent('touchstart', { bubbles: true, touches: [t(300)], changedTouches: [t(300)] }))
    el.dispatchEvent(new TouchEvent('touchend', { bubbles: true, touches: [], changedTouches: [t(120)] }))
  })
  await vw.locator('.vcount', { hasText: '1 из 4' }).waitFor()
  await vw.getByRole('button', { name: 'Закрыть' }).click()
  assert.equal(await vw.count(), 0)
  await l.locator('.ratebox').first().getByRole('button', { name: 'Оценить' }).click()
  await l.getByText('Всё оценено').waitFor()
  await l.getByRole('button', { name: '⚠ Есть вопрос' }).click()
  await l.locator('.ratebox textarea').fill('Нет чека')
  await l.getByRole('button', { name: 'Оценить' }).click()
  await l.getByText('Всё проверено').waitFor()
  const { p: hd } = await page(b, 1000, 'HEAD')
  await tab(hd, 'Проверка')
  await hd.getByText('Оценил куратор · 1').first().waitFor()
  await hd.locator('.curmark', { hasText: 'Чисто, по эскизу' }).waitFor()
  await hd.screenshot({ path: `${shots}/3-proverka-head.png`, fullPage: true })
  await hd.getByRole('button', { name: /Утвердить все с оценкой 4–5★/ }).click()
  await hd.getByText('Всё проверено').first().waitFor()
  await hd.getByRole('button', { name: '✕' }).first().click()   // расход: отказ с причиной (диалог — «Нет чека»)
  await hd.getByText('Всё проверено').nth(1).waitFor()

  // 4б. Обращение: «не внёс вовремя» — смена за прошлый день; куратор оценивает, HEAD утверждает
  await a.reload()
  await tab(a, 'Кабинет')
  await a.getByRole('button', { name: 'Не внёс вовремя' }).click()
  const yd = new Date(Date.now() - 864e5 * 2 + 5 * 36e5).toISOString().slice(0, 10)
  await a.locator('.fixbox input[type=date]').fill(yd)
  await a.locator('.fixbox textarea').first().fill('Грунт под фон')
  await a.locator('.fixbox textarea').last().fill('Не было связи на объекте')
  // HEAD 22.11: к забытой смене — несколько фото
  await a.locator('.fixbox .snapbtns input[type=file]').last().setInputFiles([__dirname + '/chek.png', __dirname + '/chek.png', __dirname + '/chek.png'])
  await a.locator('.fixbox .pics img').nth(2).waitFor()
  await a.screenshot({ path: `${shots}/6-obrashchenie.png`, fullPage: true })
  await a.locator('.fixbox').getByRole('button', { name: 'Отправить' }).click()
  await a.getByText('Обращение ушло').first().waitFor()
  await l.reload(); await tab(l, 'Проверка')
  await l.getByText('Не внёс смену').waitFor()
  await l.locator('.pics img').nth(2).waitFor()
  await l.screenshot({ path: `${shots}/6-obrashchenie-foto.png`, fullPage: true })
  await l.locator('.starpick').first().getByRole('button', { name: '4 из 5' }).click()
  await l.getByRole('button', { name: 'Оценить' }).click()
  await l.getByText('Не внёс смену').waitFor({ state: 'detached' })
  await hd.reload(); await tab(hd, 'Проверка')
  await hd.getByText('Обращения на правку').waitFor()
  await hd.screenshot({ path: `${shots}/6-obrashchenie-head.png`, fullPage: true })
  await hd.locator('.card', { hasText: 'Обращения на правку' }).getByRole('button', { name: '✓' }).click()
  await hd.getByText('Обращения на правку').waitFor({ state: 'detached' })

  // 5. «Проекты» = бывшие «Объекты» (HEAD 08.11): карточка проекта, фото с объекта и файл дизайна (большой файл — прямо в Google, здесь подменён)
  await call(1000, `/people/${(await call(1000, '/people')).find(x => x.full_name === 'Дана Ахметова').id}`, { zones: ['mural', 'design'] })
  psql("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (1700, 'ШКОЛА', 'Шымкент', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")
  await a.reload()
  await a.route('https://upload.example/**', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'drvBIG00000001' }) }))
  await tab(a, 'Проекты')
  await a.locator('.pcard', { hasText: 'Школа' }).waitFor()
  await a.screenshot({ path: `${shots}/4-proekty.png`, fullPage: true })
  await a.locator('.pcard', { hasText: 'Школа' }).click()
  await a.locator('.phero').waitFor()
  await a.locator('.dzbox').getByText(/Загрузить эскиз/).waitFor()   // эскизы — в блоке «Дизайн» (HEAD 14.11)
  await a.locator('.dzbox label.photo input[type=file]').setInputFiles({ name: 'Эскиз.psd', mimeType: 'image/vnd.adobe.photoshop', buffer: Buffer.from('PSD-DATA') })
  await a.getByText('Эскиз.psd').waitFor()
  await a.locator('.segf').getByRole('button', { name: 'Фото' }).click()
  await a.locator('label.btnlike', { hasText: 'Из галереи' }).locator('input[type=file]').setInputFiles([__dirname + '/chek.png', __dirname + '/chek.png'])
  await a.locator('.grid img').nth(1).waitFor()
  await a.screenshot({ path: `${shots}/5-kartochka-proekta.png`, fullPage: true })

  const my = await call(2000, '/my')
  assert.deepStrictEqual(my.shifts.map(s => s.status), ['approved', 'approved'])
  assert.deepStrictEqual(my.shifts.map(s => s.cur_stars), [5, 4])
  assert.ok(my.shifts[1].appeal_id && my.shifts[1].backfill)
  assert.deepStrictEqual(my.expenses.map(e => [e.status, e.reason]), [['rejected', 'Нет чека']])
  assert.strictEqual(Number(my.shifts[0].area_m2), 12.5)
  assert.ok(my.shifts[0].photo_before && my.shifts[0].photo_after && my.shifts[0].work_done)
  assert.strictEqual(my.shifts[0].complexity, 'medium')   // из сделки, не с телефона
  assert.ok(my.shifts[0].at_height && my.shifts[0].hard_surface)
  assert.match(my.expenses[0].receipt_url, /^\/api\/files\/\d+\/content\?exp=/)
  console.log('E2E OK')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

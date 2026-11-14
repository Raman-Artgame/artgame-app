// Рабочее место маркетинга (HEAD 14.11): Маркетолог ставит публикацию в контент-план с материалом из «Медиа»,
// отправляет HEAD; HEAD видит её на Пульте и в «Маркетинг → На утверждение», утверждает; маркетолог отмечает «Вышло» со ссылкой.
// Без «Утверждаю» кнопки «Вышло» нет. Скриншоты — ширина iPhone (390). API — e2e/fake_api.py.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const fs = require('fs')
const assert = require('assert')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const API = 'http://127.0.0.1:8100/api'
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const shots = process.env.SHOTS || '/var/tmp'
const IMG = process.env.IMG || '/mnt/project-files/design-kit/client-docs/assets'
const psql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "${q}"`)
const shot = async (p, n) => { await p.waitForTimeout(450); return p.screenshot({ path: `${shots}/${n}.png`, fullPage: !n.match(/new|pick|sent|review/) }) }   // лист снизу — по экрану, после анимации

async function open(b, id) {
  const ctx = await b.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  const d = sign(id)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  await p.goto('http://127.0.0.1:4173/')
  await p.locator('nav').waitFor()
  return p
}
async function tab(p, name) {
  const nav = p.locator('nav')
  const btn = nav.getByRole('button', { name, exact: true })
  if (await btn.waitFor({ timeout: 2000 }).then(() => true, () => false)) return btn.click()
  await nav.locator('button').last().click()
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}
const noScroll = async p => assert.ok(await p.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'горизонтальная прокрутка')

;(async () => {
  const b = await chromium.launch()
  await call(1000, '/register', { full_name: 'Раман Холопов' })
  const ids = {}
  for (const [tg, name, role, zones] of [[2600, 'Айгерим Маркетолог', 'marketer', ['marketing']], [3000, 'Куаныш', 'lead_artist', ['mural']]]) {
    ids[tg] = (await call(tg, '/register', { full_name: name })).id
    await call(1000, `/people/${ids[tg]}`, { role_code: role, zones })
  }
  psql("INSERT INTO objects (id, title, city, bitrix_stage) VALUES (731, 'Кафе Алма', 'Астана', 'UC_AV00QK'), (745, 'Школа №12', 'Шымкент', 'UC_AV00QK') ON CONFLICT (id) DO NOTHING")
  const media = [['wall_woman.jpg', 731, 'photo', 'approved'], ['wall_orange.jpg', 731, 'photo', 'pending'], ['wall_faces.jpg', 745, 'photo', 'approved'],
    ['do_mural.jpg', 745, 'reels', 'approved'], ['wall1.jpg', 731, 'video', 'pending']]
  for (const [i, [fn, obj, t, rv]] of media.entries()) {
    const fid = `drvMKT${i}`
    await fetch(`${API}/_e2e/store/${fid}`, { method: 'POST', headers: { 'Content-Type': 'image/jpeg' }, body: fs.readFileSync(`${IMG}/${fn}`) })
    psql(`INSERT INTO files (client_uid, object_id, kind, name, mime, size, drive_id, uploaded_by, status, media_type, review) VALUES (gen_random_uuid(), ${obj}, 'media', '${fn.replace('.jpg', '')}.jpg', 'image/jpeg', 1, '${fid}', ${ids[3000]}, 'ready', '${t}', '${rv}')`)
  }

  // 1. Маркетолог: меню, «Маркетинг» первым, план месяца пуст
  const m = await open(b, 2600)
  await m.route('https://upload.example/**', r => r.fulfill({ contentType: 'application/json', body: JSON.stringify({ id: 'drvBIG00000091' }) }))
  const nav = (await m.locator('nav button').allTextContents()).map(t => t.replace(/\d+$/, ''))
  assert.deepStrictEqual(nav, ['Маркетинг', 'Проекты', 'Кабинет', 'Чат'], nav.join(','))
  await m.getByText('В этом месяце пока пусто.').waitFor()
  await noScroll(m); await shot(m, 'mkt-1-plan-empty')
  // 2. «Медиа»: рилс по умолчанию, «Лучшее» — только утверждённое HEAD
  await m.locator('.segf').getByRole('button', { name: 'Медиа' }).click()
  await m.getByText('do_mural.jpg').waitFor()
  await m.locator('.seg').getByRole('button', { name: 'Фото' }).click()
  await m.getByText('wall_orange.jpg').waitFor()
  await m.locator('.chips').getByRole('button', { name: 'Лучшее' }).click()
  await m.getByText('wall_faces.jpg').waitFor()
  await m.getByText('wall_orange.jpg').waitFor({ state: 'detached' })   // «Лучшее» — без ждущего HEAD (wall_faces виден и до переключения — ждём, пока список обновится)
  await noScroll(m); await shot(m, 'mkt-2-media')
  // 3. Новая публикация: название, Instagram/Рилс, дата, текст, проект, материал
  await m.locator('.segf').getByRole('button', { name: 'План' }).click()
  await m.getByRole('button', { name: '+ Публикация' }).click()
  const s = m.locator('.sheetbox')
  await s.getByPlaceholder('Например').fill('Рилс «Кафе Алма — до и после»')
  const d = new Date(); const day = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-20`
  await s.locator('input[type=date]').fill(day)
  await s.locator('textarea').fill('Было серо — стало Алма 🌿\nРоспись ARTGAME за 5 смен.\n#роспись #астана')
  await s.locator('select').selectOption('731')
  await shot(m, 'mkt-3-new')
  await s.getByRole('button', { name: '🎬 Выбрать из «Медиа»' }).click()
  await m.locator('.sheetbox').getByText('do_mural.jpg').waitFor()
  await m.locator('.sheetbox').getByRole('button', { name: 'Выбрать' }).first().click()
  await shot(m, 'mkt-4-pick')
  await m.locator('.sheetbox').getByRole('button', { name: /Готово · выбрано 1/ }).click()
  // «Загрузить готовое»: файл агентства идёт прямо в Google (подменён), встаёт в публикацию рядом с выбранным
  await m.locator('.sheetbox label.mktup input[type=file]').setInputFiles({ name: 'Рилс готовый.mp4', mimeType: 'video/mp4', buffer: Buffer.from('MP4-DATA') })
  await m.locator('.sheetbox').getByText('Материал · 2').waitFor()
  await shot(m, 'mkt-4b-ready-new')
  await m.locator('.sheetbox').getByRole('button', { name: 'Сохранить' }).click()
  await m.locator('.sheetbox').getByRole('button', { name: 'Отправить HEAD' }).waitFor()
  assert.strictEqual(await m.locator('.sheetbox').getByRole('button', { name: 'Вышло' }).count(), 0)   // черновик не выложить
  await m.locator('.sheetbox').getByRole('button', { name: 'Отправить HEAD' }).click()
  await m.locator('.sheetbox .badge', { hasText: 'у HEAD' }).waitFor()
  await shot(m, 'mkt-5-sent')
  await m.locator('.sheetbox .x').click()

  // 4. HEAD: на Пульте «Публикации на утверждение: 1» → «Маркетинг → На утверждение» → «Утверждаю»
  const h = await open(b, 1000)
  await h.getByText('Публикации на утверждение: 1').waitFor()
  await shot(h, 'mkt-6-head-pulse')
  // ещё две сторис на тот же день и одна на другой — для ленты и «Утвердить все»
  for (const [t, dd] of [['Сторис: утро на объекте', '20'], ['Сторис: отзыв клиента', '20'], ['Пост: команда', '22']]) {
    const x = await call(2600, '/mkt/posts', { title: t, kind: t.startsWith('Пост') ? 'post' : 'stories', plan_date: day.slice(0, 8) + dd, caption: 'Текст для ' + t })
    await call(2600, `/mkt/posts/${x.id}/submit`, {})
  }
  await h.getByText('Публикации на утверждение: 1').click()
  await h.locator('.mktfeed').getByText('1 из 4').waitFor()
  await h.locator('.mktfeed').getByRole('button', { name: 'Утверждаю' }).waitFor()
  await noScroll(h); await shot(h, 'mkt-7-head-feed')
  await h.locator('.mktfeed').getByRole('button', { name: 'Вернуть' }).click()
  await h.locator('.mktfeed input').fill('Проверка')
  await shot(h, 'mkt-7a-head-back')
  await h.locator('.mktfeed').getByRole('button', { name: 'Отмена' }).click()
  await h.locator('.mktfeed').getByRole('button', { name: /Утвердить все 3 на/ }).click()
  await h.locator('.mktfeed').getByText('1 из 1').waitFor()
  await h.locator('.mktfeed .mkttitle', { hasText: 'Пост: команда' }).waitFor()
  await shot(h, 'mkt-7c-head-text')
  await h.locator('.mktfeed').getByRole('button', { name: 'Вернуть' }).click()
  await h.locator('.mktfeed input').fill('Добавь фото команды')
  await h.locator('.mktfeed').getByRole('button', { name: 'Вернуть на доработку' }).click()
  await h.getByText('Всё утверждено.').waitFor()
  await shot(h, 'mkt-7d-head-empty')

  // 5. Маркетолог: «Вышло» со ссылкой → в плане «вышло»
  await m.reload(); await m.locator('nav').waitFor()
  await m.getByText('Рилс «Кафе Алма — до и после»').click()
  await m.locator('.sheetbox').getByRole('button', { name: /Для TikTok/ }).waitFor()
  await shot(m, 'mkt-7e-tiktok-sent')
  await m.locator('.sheetbox').getByPlaceholder('https://instagram.com/…').fill('https://instagram.com/reel/abc')
  await m.locator('.sheetbox').getByRole('button', { name: 'Вышло' }).click()
  await m.locator('.sheetbox').getByText('Открыть публикацию ›').waitFor()
  // итог: просмотры, заявки, «Дала результат»
  await m.locator('.sheetbox').getByPlaceholder('Просмотры').fill('12400')
  await m.locator('.sheetbox').getByPlaceholder('Заявки').fill('3')
  await m.locator('.sheetbox').getByPlaceholder('Что сработало / что нет').fill('до/после заходит, 2 заявки из директа')
  await m.locator('.sheetbox').getByRole('button', { name: 'Дала результат' }).click()
  await m.locator('.mktrow .badge', { hasText: 'дала результат' }).waitFor({ state: 'attached' })
  await shot(m, 'mkt-7b-result')
  await m.locator('.sheetbox .x').click()
  await m.locator('.mktrow .badge', { hasText: 'вышло' }).waitFor()
  await noScroll(m); await shot(m, 'mkt-8-plan')
  // 7. Идеи и съёмки: сценарий → съёмка вне проектов с оператором → идея «в работе»
  await m.locator('.segf').getByRole('button', { name: 'Идеи' }).click()
  await m.getByRole('button', { name: '+ Идея' }).click()
  await m.locator('.sheetbox').getByPlaceholder('Например').fill('Говорящая голова: HEAD о том, как рождается роспись')
  await m.locator('.sheetbox textarea').fill('1. HEAD у стены, крупно руки\n2. Таймлапс эскиза\n3. Итог и призыв')
  await shot(m, 'mkt-11-idea')
  await m.locator('.sheetbox').getByRole('button', { name: 'Сохранить' }).click()
  await m.getByText('Говорящая голова: HEAD').waitFor()
  await noScroll(m); await shot(m, 'mkt-12-ideas')
  await m.locator('.segf').getByRole('button', { name: 'Съёмки' }).click()
  await m.getByRole('button', { name: '+ Съёмка' }).click()
  const sh = m.locator('.sheetbox')
  await sh.getByPlaceholder('Что снимаем').fill('Интервью HEAD в студии')
  await sh.locator('input[type=date]').fill(day.slice(0, 8) + '18')
  await sh.getByPlaceholder('Время').fill('11:00')
  await sh.getByPlaceholder('Место').fill('Студия, Кабанбай батыра 5')
  await sh.locator('.chips').getByRole('button', { name: 'Айгерим Маркетолог' }).click()
  await sh.locator('select').nth(1).selectOption({ label: 'Говорящая голова: HEAD о том, как рождается роспись' })
  await shot(m, 'mkt-13-shoot')
  await sh.getByRole('button', { name: 'Сохранить' }).click()
  await m.getByText('11:00 · Интервью HEAD в студии').waitFor()
  await noScroll(m); await shot(m, 'mkt-14-shoots')
  await m.locator('.segf').getByRole('button', { name: 'Идеи' }).click()
  await m.locator('.mktidea .badge', { hasText: 'в работе' }).waitFor()
  // 6. Кабинет маркетолога и «Команда» у HEAD — отдел «Маркетинг»
  await tab(m, 'Кабинет'); await m.waitForTimeout(500); await noScroll(m); await shot(m, 'mkt-9-kabinet')
  await tab(h, 'Команда'); await h.getByText('Маркетинг').first().waitFor(); await shot(h, 'mkt-10-komanda')
  const posts = await call(1000, `/mkt/posts?ym=${day.slice(0, 7)}`)
  assert.strictEqual(posts.counts.published, 1); assert.strictEqual(posts.counts.approved, 2); assert.strictEqual(posts.counts.rejected, 1)
  console.log('marketing ok')
  await b.close()
})().catch(e => { console.error(e); process.exit(1) })

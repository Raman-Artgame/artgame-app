// Снимки всех вкладок всех ролей на заданной ширине (HEAD 26.11: версия для компьютера).
// node e2e/shirina.cjs <ширина> <папка> — телефон сверяем «до/после» по пикселям, компьютер смотрим глазами.
const { chromium } = require('playwright')
const { execSync } = require('child_process')
const fs = require('fs')
const BE = __dirname + '/../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const sign = id => execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim()
const W = +process.argv[2] || 390, OUT = process.argv[3] || '/var/tmp/shots', H = W < 700 ? 780 : W >= 1900 ? 1000 : 900
const ONLY = (process.env.ROLES || '').split(',').filter(Boolean)
const ROLES = [['support', 7100], ['artist', 7101], ['artist_pro', 7102], ['lead_artist', 7103], ['print_operator', 7104], ['print_master', 7105],
  ['mop', 7106], ['lead_designer', 7107], ['designer_asst', 7108], ['carpenter', 7109], ['head', 1000]].filter(r => !ONLY.length || ONLY.includes(r[0]))
const freeze = () => { const s = document.createElement('style'); s.textContent = '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}'; document.head.appendChild(s) }
;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const b = await chromium.launch()
  for (const [role, id] of ROLES) {
    const ctx = await b.newContext({ viewport: { width: W, height: H } })
    const pg = await ctx.newPage()
    const d = sign(id)
    await pg.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {} } } }, d)
    await pg.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
    pg.on('dialog', dl => dl.dismiss())
    await pg.goto('http://127.0.0.1:4173/')
    await pg.locator('nav').waitFor()
    await pg.evaluate(freeze)
    const names = (await pg.locator('nav button').allTextContents()).map(t => t.replace(/\d+$/, ''))
    const more = names[names.length - 1] === 'Ещё'
    let extra = []
    if (more) { await pg.locator('nav button').last().click(); await pg.waitForTimeout(300); extra = await pg.locator('.sheetbox button').allTextContents(); await pg.mouse.click(5, 5); await pg.waitForTimeout(200) }
    const all = [...(more ? names.slice(0, -1) : names), ...extra]
    for (let i = 0; i < all.length; i++) {
      const name = all[i]
      const btn = pg.locator('nav button', { hasText: new RegExp(`^${name}\\d*$`) })
      if (await btn.count()) await btn.first().click()
      else { await pg.locator('nav button').last().click(); await pg.waitForTimeout(300); await pg.locator('.sheetbox button', { hasText: name }).first().click() }
      await pg.waitForTimeout(1200)
      await pg.screenshot({ path: `${OUT}/${role}-${String(i).padStart(2, '0')}-${name}.png`, fullPage: process.env.FULL !== '0' })
    }
    await ctx.close()
  }
  await b.close()
  console.log('OK', W, OUT)
})().catch(e => { console.error(e); process.exit(1) })

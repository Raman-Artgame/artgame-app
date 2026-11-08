// Общее для обучающих роликов (HEAD 08.11): стенд на fake_api.py, люди всех ролей, объекты, «Значения».
// Запуск стенда — app/README.md (fake_api.py + vite preview). Числа «Значений» берутся из CONSTS (снимок листа), в код не вшиваются.
const { execSync } = require('child_process')
const fs = require('fs')
const BE = __dirname + '/../../backend'
const PY = process.env.PY || `${BE}/.venv/bin/python`
const API = 'http://127.0.0.1:8100/api'
const _sig = {}
const sign = id => _sig[id] || (_sig[id] = execSync(`cd ${BE} && ${PY} -c "import sys;sys.path+=['tests'];from conftest import make_init_data;print(make_init_data({'id':${id},'first_name':'Тест'}))"`).toString().trim())
const call = async (id, path, body) => (await fetch(API + path, { method: body ? 'POST' : 'GET',
  headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': sign(id) }, body: body && JSON.stringify(body) })).json()
const psql = q => execSync(`psql "${process.env.ARTGAME_DATABASE_URL}" -qc "${q.replace(/"/g, '\\"')}"`)

// tg-id → [имя, роль, зоны, id в Битриксе]
const PEOPLE = {
  1000: ['Раман', 'head', ['mural', 'print', 'design', 'sales'], 17],
  2000: ['Нурлан', 'support', ['mural'], 0],
  2100: ['Дана', 'artist', ['mural'], 0],
  3000: ['Ержан', 'lead_artist', ['mural'], 0],
  4000: ['Айбек', 'artist_pro', ['mural'], 0],
  5000: ['Аян', 'print_operator', ['print'], 0],
  5100: ['Тимур', 'print_master', ['print'], 0],
  6000: ['Ануар', 'mop', ['sales'], 4565],
  7000: ['Алия', 'lead_designer', ['design'], 4565],
  7100: ['Мира', 'designer_asst', ['design'], 4693],
}

async function seed(only) {
  if (process.env.CONSTS) await call(1000, '/_e2e/consts', JSON.parse(fs.readFileSync(process.env.CONSTS, 'utf8')))
  const ids = {}
  for (const [tg, [name, role, zones, bxu]] of Object.entries(PEOPLE)) {
    if (only && tg !== '1000' && !only.includes(+tg)) continue
    ids[tg] = (await call(+tg, '/register', { full_name: name, phone: '+7 701 000 00 ' + String(tg).slice(0, 2) })).id
    if (role !== 'head') await call(1000, `/people/${ids[tg]}`, { role_code: role, zones, ...(bxu ? { bitrix_user_id: bxu } : {}) })
  }
  psql("INSERT INTO objects (id, title, city, bitrix_stage, level, area_m2, address, geo, drive_folder) VALUES (731, 'Кафе «Тюльпан»', 'Астана', 'UC_AV00QK', 'medium', 60, 'Мангилик Ел 1', '51.09;71.41', 'deal-731') ON CONFLICT (id) DO UPDATE SET bitrix_stage='UC_AV00QK', level='medium', title='Кафе «Тюльпан»', area_m2=60, address='Мангилик Ел 1', geo='51.09;71.41', drive_folder='deal-731'")
  psql(`INSERT INTO deal_calc (deal_id, data) VALUES (731, '{"in": {"service": "mural", "level": "medium", "extras": ["height"], "surface": true}}') ON CONFLICT DO NOTHING`)
  psql("INSERT INTO objects (id, title, city, bitrix_stage, level, area_m2, address) VALUES (1700, 'Школа № 12', 'Шымкент', 'UC_AV00QK', 'hard', 120, 'Тауке хана 40') ON CONFLICT (id) DO NOTHING")
  psql("INSERT INTO objects (id, title, city, bitrix_stage, level, area_m2, address) VALUES (812, 'ЖК «Нурлы» — печать', 'Астана', 'UC_AV00QK', 'easy', 45, 'Туран 55') ON CONFLICT (id) DO NOTHING")
  psql(`INSERT INTO deal_calc (deal_id, data) VALUES (812, '{"in": {"service": "print"}}') ON CONFLICT DO NOTHING`)
  return ids
}

const OVERLAY = () => {   // красный круг на каждом нажатии
  const css = `.tdot{position:fixed;z-index:2147483646;width:38px;height:38px;margin:-19px 0 0 -19px;border-radius:50%;border:3px solid #E60041;background:rgba(230,0,65,.22);pointer-events:none;animation:tdot .75s ease-out forwards}
    @keyframes tdot{from{transform:scale(.4);opacity:1}to{transform:scale(1.5);opacity:0}} ::-webkit-scrollbar{display:none}`
  const put = () => { if (!document.head || document.getElementById('tdotcss')) return
    const s = document.createElement('style'); s.id = 'tdotcss'; s.textContent = css; document.head.appendChild(s) }
  document.addEventListener('DOMContentLoaded', put); setInterval(put, 300)
  document.addEventListener('pointerdown', e => { const d = document.createElement('div'); d.className = 'tdot'; d.style.left = e.clientX + 'px'; d.style.top = e.clientY + 'px'; document.body.appendChild(d); setTimeout(() => d.remove(), 900) }, true)
}

const VP = { width: 390, height: 780 }
// Запись экрана: CDP-скринкаст в настоящем разрешении (×2), кадры JPEG с отметкой времени → video.cjs собирает mp4.
async function open(b, tg, video, vp = VP, path = '/') {
  const ctx = await b.newContext({ viewport: vp, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  if (video) {
    fs.mkdirSync(video + '/frames', { recursive: true })
    const cdp = await ctx.newCDPSession(p); const list = []; let n = 0
    cdp.on('Page.screencastFrame', async f => {
      const name = `frames/${String(n++).padStart(6, '0')}.jpg`
      fs.writeFileSync(video + '/' + name, Buffer.from(f.data, 'base64')); list.push([name, f.metadata.timestamp])
      cdp.send('Page.screencastFrameAck', { sessionId: f.sessionId }).catch(() => {})
    })
    await cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: vp.width * 2, maxHeight: vp.height * 2, everyNthFrame: 1 })
    p.__stopRec = async () => { await cdp.send('Page.stopScreencast').catch(() => {}); fs.writeFileSync(video + '/frames.json', JSON.stringify(list)) }
  }
  const d = sign(tg)
  await p.addInitScript(d => { window.Telegram = { WebApp: { initData: d, initDataUnsafe: { user: { first_name: 'Т' } }, ready() {}, expand() {} } } }, d)
  await p.addInitScript(OVERLAY)
  await p.route('https://telegram.org/**', r => r.fulfill({ body: '' }))
  p.on('dialog', dl => dl.accept('ок'))
  await p.goto('http://127.0.0.1:4173' + path)
  await p.locator('nav').waitFor({ timeout: 20000 })
  return { p, ctx }
}
async function tab(p, name) {
  const nav = p.locator('nav')
  const btn = nav.getByRole('button', { name: new RegExp(`^${name}\\s*\\d*$`) })
  if (await btn.count()) { await btn.first().scrollIntoViewIfNeeded(); return btn.first().click() }
  await nav.locator('button').last().click(); await p.waitForTimeout(700)
  await p.locator('.sheetbox').getByRole('button', { name, exact: true }).click()
}
const navText = async p => (await p.locator('nav button').allTextContents()).map(t => t.replace(/\d+$/, '').trim())
module.exports = { sign, call, psql, seed, open, tab, navText, PEOPLE, VP, API }

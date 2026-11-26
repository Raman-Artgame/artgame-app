import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { CityPicker, Sheet } from './ui.jsx'

// Заполненность карточки сделки (HEAD 06.11): МОП заполняет все утверждённые поля, ИИ помогает.
// Полоса в шапке — «заполнено нужного»; окно «Заполнить карточку» — ИИ разбирает переписку/анкету, МОП проверяет и записывает.
export const STEP_NAME = { client: 'Клиент', calc: 'Расчёт', kp: 'КП', docs: 'Договор', pay: 'Оплата', work: 'В работе' }
const STEP_ORDER = ['client', 'calc', 'kp', 'docs', 'pay', 'work']
const STAGE_STEP = { NEW: 0, PREPARATION: 2, UC_VZFPUP: 2, UC_YV66BV: 2, UC_1EXUAC: 2, UC_VCP4VO: 0, FINAL_INVOICE: 3, UC_AV00QK: 5, UC_BMKDS4: 5, WON: 5 }
export const anketaKey = id => `artgame.deal.anketa.${id}`

// Замок (HEAD 06.11 «не чек-лист, а чтобы всё заполнялось»): сервер присылает, что обязательно на какой стадии (required),
// приложение не даёт перейти дальше, пока не заполнено. HEAD (free) замок не держит. Сервер проверяет то же самое ещё раз.
export function lockFor(fill, keys) {
  if (!fill || fill.free) return []
  const ok = new Set(fill.items.filter(x => x.ok).map(x => x.key))
  const lab = Object.fromEntries(fill.items.map(x => [x.key, x.label]))
  return keys.filter(k => !ok.has(k)).map(k => lab[k])
}
export const LOCK_KP = ['name', 'phone', 'city', 'service', 'address', 'area', 'sum', 'calc']
export const LOCK_DOCS = [...LOCK_KP, 'kp']   // аванс, срок и гарантию даёт сам договор

export function missingFor(fill, cur, target) {
  if (!fill?.required) return []
  const st = fill.step_of || {}
  if ((st[target] ?? 0) <= (st[cur] ?? 0) && target !== 'WON') return []
  return lockFor(fill, fill.required[target] || [])
}

// Плашка «Сначала заполните» вместо КП/договора, пока карточка пустая.
export function Locked({ miss, what, onFill, onCalc }) {
  const calc = miss.some(m => m.startsWith('Расчёт') || m.startsWith('Сумма'))
  return <div className="lockbox">
    <b>🔒 {what} откроется, когда заполнено:</b>
    <div>{miss.map(m => <span key={m} className="miss">{m}</span>)}</div>
    <div className="dealbtns wrapbtns">
      <button className="mini" onClick={onFill}>Заполнить карточку</button>
      {calc && onCalc && <button className="ghost mini" onClick={onCalc}>К расчёту</button>}
    </div>
  </div>
}

export function FillBar({ fill, onOpen }) {
  if (!fill || !fill.missing.length) return null
  const pct = fill.need ? Math.round(fill.need_done / fill.need * 100) : 100
  return <div className="fillbar" onClick={onOpen} role="button">
    <div className="fb-top"><span>Обязательно заполнить</span><b>{fill.need_done} из {fill.need}</b></div>
    <div className="fb-line"><i style={{ width: pct + '%' }} /></div>
    <div className="fb-miss">{fill.missing.slice(0, 4).join(', ') + (fill.missing.length > 4 ? ` и ещё ${fill.missing.length - 4}` : '')} — без этого сделка дальше не пойдёт</div>
    <button className="mini fb-go">Заполнить недостающее</button>
  </div>
}

// Окно «Карточка сделки» (схема HEAD 26.11 «кто что заполняет», «во всём остальном окей, давай попробуем»):
// каждое значение вводится в одном месте. Здесь МОП вводит только «Клиент и проект». Цена и нормы — из калькулятора,
// КП — из расчёта, дизайн — из задачи дизайнера, договор — из бланка договора, оплата — с чеком, куратор ГИП, старт
// и сдача — «В производство», художников ставит куратор ГИП. Всё это видно здесь итогом, с кнопкой «куда идти».
// Подкатегория — только из своей категории: категория N (по порядку в Битриксе) ↔ подкатегории «N.x».
const EDIT = ['object', 'city', 'service', 'address', 'area', 'category', 'subcategory', 'entry', 'model', 'size', 'vip']
const LABEL = { object: 'Объект', city: 'Город', service: 'Услуга', category: 'Категория', subcategory: 'Подкатегория', entry: 'Точка входа',
  address: 'Адрес объекта', area: 'Площадь, м²', model: 'Модель', size: 'Размер проекта', vip: 'VIP-клиент' }
const PROJ = ['category', 'subcategory', 'entry', 'model', 'size', 'vip']
const CHIPS = ['model', 'size']
const LEVEL = { easy: 'Лёгкий', medium: 'Средний', hard: 'Сложный', author: 'Авторский' }
const fmt = v => v ? Number(v).toLocaleString('ru-RU').replace(/,/g, ' ') + ' ₸' : '—'
const day = v => v ? String(v).slice(0, 10).split('-').reverse().join('.') : ''
// итог шага: строки только для чтения и кнопка, где это заполняется
function Info({ rows, children }) {
  return <div className="fillinfo" style={{ gridColumn: '1 / -1' }}>
    {rows.map(([k, v, bad]) => <div key={k} className="row"><span className="muted small">{k}</span><span className={bad ? 'why' : ''}>{v || '—'}</span></div>)}
    {children && <div className="dealbtns wrapbtns">{children}</div>}
  </div>
}
// шаг окна; вне FillSheet, чтобы поля не пересоздавались при каждом вводе (иначе слетает фокус)
function Sec({ title, n, tag, children }) {
  return <div className="fillgrid">
    <h3 className="fillsec">{title}{tag && <i className="srctag">{tag}</i>}{n ? <i className="needtag">нужно {n}</i> : null}</h3>{children}</div>
}
export const subsOf = (cats, subs, catId) => {
  const i = (cats || []).findIndex(o => o.id === catId)
  return i < 0 ? [] : (subs || []).filter(o => (o.name || '').trim().startsWith(`${i + 1}.`))
}

export function FillSheet({ d, onClose, onDone, onClient, onStep, onDesign, onProd }) {
  const by = Object.fromEntries((d.fill?.items || []).map(x => [x.key, x]))
  const [f, setF] = useState({ object: d.object || '', cityName: d.city || '', city: '', service: '', area: d.area || '', address: d.address || '' })
  const [pr, setPr] = useState(() => ({ ...(d.project || {}) }))
  const [ai, setAi] = useState({})          // какие поля подставил помощник
  const [dict, setDict] = useState({ cities: [], services: [], project: null })
  const [helper, setHelper] = useState(false)
  const [text, setText] = useState(() => { try { return localStorage.getItem(anketaKey(d.id)) || '' } catch { return '' } })
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  const [gip, setGip] = useState(null)      // куратор ГИП — только показать (ставит «В производство»)
  const [dt, setDt] = useState(null)        // задачи на дизайн
  useEffect(() => { api('/bx/dict').then(x => { setDict(x); const s = x.services.find(s => s.name === d.service); setF(v => ({ ...v, service: s?.id || '' })) }, () => {}) }, [])
  useEffect(() => {
    api(`/bx/deals/${d.id}/gip`).then(r => setGip((r.candidates || []).find(o => o.id === r.gip_id)?.full_name || ''), () => setGip(''))
    api(`/bx/deals/${d.id}/design-tasks`).then(r => setDt(r.items || []), () => setDt([]))
  }, [d.id])
  const have = k => !PROJ.includes(k) || (dict.project?.have || []).includes(k)
  const need = k => by[k]?.need && !by[k]?.ok
  const set = (k, v) => { setF(x => ({ ...x, [k]: v })); setAi(a => ({ ...a, [k]: false })) }
  const parse = () => {
    setBusy('parse'); setMsg('')
    try { localStorage.setItem(anketaKey(d.id), text) } catch { /* без памяти */ }
    api(`/bx/deals/${d.id}/extract`, { method: 'POST', body: { text } }).then(r => {
      const x = r.fields, put = {}, mark = {}
      if (x.city) { put.city = x.city; put.cityName = x.cityName; mark.city = true }
      if (x.service) { put.service = x.service; mark.service = true }
      for (const k of ['area', 'address']) if (x[k]) { put[k] = x[k]; mark[k] = true }
      setF(v => ({ ...v, ...put })); setAi(mark); setHelper(false)
      setMsg(`Подставлено полей: ${Object.keys(mark).length} — отмечены «ИИ». Проверьте и запишите.` + (r.client && Object.values(r.client).some(Boolean) ? ' Имя, телефон и реквизиты — в «Клиент и реквизиты».' : ''))
    }, e => setMsg(e.message)).finally(() => setBusy(''))
  }
  // что записать: только изменённое
  const body = {}
  if (f.object.trim() && f.object.trim() !== (d.object || '')) body.object = f.object.trim()
  if (f.city && f.cityName !== d.city) body.city = f.city
  if (f.service && (dict.services.find(s => s.id === f.service)?.name || '') !== (d.service || '')) body.service = f.service
  if (+f.area && +f.area !== (d.area || 0)) body.area = +f.area
  if (f.address && f.address !== (d.address || '')) body.address = f.address
  const p0 = d.project || {}
  const same = (a, b) => String(a ?? '') === String(b ?? '')
  const prj = Object.fromEntries(PROJ.filter(k => have(k) && !same(pr[k], p0[k])).map(k => [k, k === 'vip' ? !!pr[k] : pr[k] || null]))
  if (Object.keys(prj).length) body.project = prj
  const n = Object.keys(body).length - (body.project ? 1 : 0) + Object.keys(prj).length
  const save = async () => {
    setBusy('save')
    try {
      const r = await api(`/bx/deals/${d.id}/fields`, { method: 'POST', body })
      onDone(r?.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Карточка записана в Битрикс.')
    } catch (e) { setMsg('Не записалось: ' + e.message); setBusy('') }
  }

  const pd = dict.project || {}
  const subs = subsOf(pd.category, pd.subcategory, pr.category)
  const opts = { category: pd.category || [], subcategory: subs, entry: pd.entry || [] }
  const users = pd.users || []
  const uname = id => users.find(u => u.id === String(id))?.name || ''
  const ename = (k, id) => (pd[k] || []).find(o => o.id === String(id))?.name || ''
  const setP = (k, v) => setPr(x => {
    const n = { ...x, [k]: v }
    if (k === 'category' && !subsOf(pd.category, pd.subcategory, v).some(o => o.id === x.subcategory)) n.subcategory = ''   // чужая подкатегория — сброс
    return n
  })
  const field = k => {
    const filled = PROJ.includes(k) ? pr[k] : k === 'city' ? (f.city || f.cityName) : f[k]
    const cls = (ai[k] ? 'ai ' : '') + (need(k) && !filled ? 'need' : '')
    const lab = <span>{LABEL[k]}{ai[k] && <i className="aitag">ИИ</i>}{need(k) && !filled && <i className="needtag">нужно</i>}</span>
    if (k === 'city') return <CityPicker key={k} cities={dict.cities} value={f.city || dict.cities.find(c => c.name === f.cityName)?.id || ''} need={need(k) && !filled}
      label="Город" onPick={(id, name) => { setF(x => ({ ...x, city: id, cityName: name })); setAi(a => ({ ...a, city: false })) }} />
    if (CHIPS.includes(k)) return <div key={k} className={'fillchips ' + cls}><span className="cplabel">{lab}</span><div className="chips">
      {(pd[k] || []).map(o => <button key={o.id} className={pr[k] === o.id ? 'on' : ''} onClick={() => setP(k, pr[k] === o.id ? '' : o.id)}>{o.name}</button>)}</div></div>
    if (k === 'vip') return <label key={k} className="check"><span>{LABEL[k]}</span><input type="checkbox" checked={!!pr.vip} onChange={e => setP('vip', e.target.checked)} /></label>
    if (k === 'subcategory') return <label key={k} className={cls}>{lab}<select value={pr[k] || ''} disabled={!pr.category} onChange={e => setP(k, e.target.value)}>
      <option value="">{pr.category ? '—' : 'сначала категория'}</option>{subs.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
    if (PROJ.includes(k)) return <label key={k} className={cls}>{lab}<select value={pr[k] || ''} onChange={e => setP(k, e.target.value)}>
      <option value="">—</option>{opts[k].map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
    if (k === 'service') return <label key={k} className={cls}>{lab}<select value={f.service} onChange={e => set('service', e.target.value)}><option value="">—</option>{dict.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
    if (k === 'object') return <label key={k} className={cls} style={{ gridColumn: '1 / -1' }}>{lab}<input value={f.object} onChange={e => set('object', e.target.value)} placeholder="«Школа №12», «Кофейня Daily» — из него название сделки" /></label>
    if (k === 'address') return <label key={k} className={cls}>{lab}<input value={f.address} onChange={e => set('address', e.target.value)} placeholder="Улица, дом" /></label>
    return <label key={k} className={cls}>{lab}<input type="number" min="0" inputMode="decimal" value={f[k]} onChange={e => set(k, e.target.value)} /></label>
  }
  const miss = (d.fill?.items || []).filter(x => x.need && !x.ok)
  const c = d.client || {}, ka = d.kp_agreed
  const nn = keys => keys.filter(need).length
  const t = (dt || []).slice(-1)[0]
  const art = (p0.artists || []).map(uname).filter(Boolean).join(', ')
  const working = ['UC_AV00QK', 'UC_BMKDS4', 'WON'].includes(d.stage)
  return <Sheet title="Карточка сделки" onClose={onClose} wide>
    <div className="fillform">
      {miss.length ? <p className="small">Не хватает: <b>{miss.length}</b> — {miss.map(x => x.label).join(', ')}.</p> : <p className="small ok">Всё нужное заполнено.</p>}
      <p className="small muted">Здесь вводится только «Клиент и проект». Остальное приходит со своих шагов — ниже видно итог и куда идти.</p>
      <Sec title="Клиент и проект" n={nn(EDIT.concat(['name', 'phone', 'requisites']))} tag="вводит МОП">
        <Info rows={[['Клиент', c.name ? (c.type && !c.name.startsWith(c.type) ? `${c.type} · ${c.name}` : c.name) : '', need('name')], ['Телефон', c.phone, need('phone')],
          ['БИН / ИИН', c.type === 'Физлицо' ? 'не нужен' : d.requisites?.cbin, need('requisites')]]}>
          {onClient && <button className="ghost mini" onClick={onClient}>Клиент и реквизиты</button>}</Info>
        <div style={{ gridColumn: '1 / -1' }}>
          <button className="ghost mini" onClick={() => setHelper(!helper)}>{helper ? 'Скрыть помощника' : 'Вставить переписку — помощник заполнит сам'}</button>
          {helper && <div className="aibox">
            <textarea rows={5} value={text} onChange={e => setText(e.target.value)} placeholder="Переписка из WhatsApp или анкета клиента: «нужна роспись в детском саду, Астана, Кенесары 40, примерно 45 м²…»" />
            <button className="mini" disabled={text.trim().length < 10 || !!busy} onClick={parse}>{busy === 'parse' ? 'Разбираю…' : 'Разобрать'}</button>
          </div>}
          {msg && <p className="small">{msg}</p>}
        </div>
        {EDIT.filter(have).map(field)}
        <button style={{ gridColumn: '1 / -1' }} disabled={!n || !!busy} onClick={save}>{busy === 'save' ? 'Записываю…' : `Записать в Битрикс${n ? ` (${n})` : ''}`}</button>
      </Sec>
      <Sec title="Расчёт и КП" n={nn(['sum', 'calc', 'kp'])} tag="калькулятор">
        <Info rows={[['Сумма сделки', d.sum ? fmt(d.sum) : '', need('sum')], ['Сложность', LEVEL[d.level] || ''],
          ['Смен / художников по норме', d.norm?.shifts ? `${d.norm.shifts} / ${d.norm.crew || '—'}` : '', need('calc')], ['Срок, рабочих дней', d.norm?.term || ''],
          ['КП в сделке', by.kp?.ok ? 'есть' : 'нет', need('kp')], ['Клиент согласовал', ka ? `${day(ka.at)} · ${fmt(ka.total)} · закреплено` : 'нет']]}>
          {onStep && !ka && <button className="ghost mini" onClick={() => onStep('calc')}>{d.sum ? 'К расчёту' : 'Посчитать цену и срок'}</button>}
          {onStep && <button className="ghost mini" onClick={() => onStep('kp')}>К КП</button>}</Info>
      </Sec>
      <Sec title="Дизайн" n={nn([])} tag="дизайнер">
        <Info rows={[['Задач на дизайн', dt === null ? '…' : dt.length ? `${dt.length} · ${t.stage_name}` : 'нет'],
          ['Дизайнер', t?.designer || uname(p0.designer)], ['Сложность дизайна', (t?.size || '').toUpperCase() || ename('design_level', p0.design_level)],
          ['Срок дизайна', day(t?.deadline || p0.design_deadline)]]}>
          {onDesign && <button className="ghost mini" onClick={onDesign}>К блоку «Дизайн»</button>}</Info>
      </Sec>
      <Sec title="Договор" n={nn(['adv', 'days', 'warranty'])} tag="бланк договора">
        <Info rows={[['Номер договора', p0.contract_no || ''], ['Аванс', by.adv?.value ? by.adv.value + '%' : '', need('adv')],
          ['Срок по договору, дней', by.days?.value || '', need('days')], ['Гарантия, мес.', by.warranty?.value || '', need('warranty')]]}>
          {onStep && <button className="ghost mini" onClick={() => onStep('docs')}>К договору</button>}</Info>
      </Sec>
      <Sec title="Оплата" n={nn(['paid', 'signed'])} tag="с чеком">
        <Info rows={[['Поступило', fmt(d.pay?.received), need('paid')], ['Долг', d.pay?.debt ? fmt(d.pay.debt) : '0 ₸'],
          ['Подписанный договор', by.signed?.ok ? 'есть' : 'нет', need('signed')]]}>
          {onStep && <button className="ghost mini" onClick={() => onStep('pay')}>К оплате</button>}</Info>
      </Sec>
      <Sec title="Производство" n={nn(['start', 'end'])} tag="«В производство»">
        <Info rows={[['Куратор ГИП', gip === null ? '…' : gip], ['Старт работ', day(by.start?.value), need('start')], ['Сдача (план)', day(by.end?.value), need('end')],
          ['Художники', art || (working ? 'ставит куратор ГИП' : '')]]}>
          {onProd && !working && <button className="ghost mini" onClick={onProd}>В производство</button>}
          {onStep && working && <button className="ghost mini" onClick={() => onStep('work')}>К проекту</button>}</Info>
      </Sec>
    </div>
  </Sheet>
}

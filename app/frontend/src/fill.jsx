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

// Окно «Карточка сделки» (HEAD 26.11 «заполнение карточки по всем нашим изменениям, сейчас намешано старое и новое»):
// все поля карточки по шагам сделки. Нехватающее помечено «нужно» и стоит первым в своём шаге. Имя, телефон и
// реквизиты — в «Клиент и реквизиты», расчёт — в шаге «Расчёт». Подсказок «куда нажать» нет: всё заполняется здесь.
// HEAD 26.11: в сделке только «Куратор ГИП» (назначает ГИП объекта); «Ответственный исполнитель» из окна убран, в Битриксе остаётся.
// Подкатегория — только из своей категории: категория N (по порядку в Битриксе) ↔ подкатегории «N.x».
const SECTIONS = [
  ['client', 'Клиент и объект', ['object', 'city', 'service', 'category', 'subcategory', 'entry', 'address', 'area']],
  ['project', 'Проект', ['model', 'size', 'vip']],
  ['calc', 'Расчёт и КП', []],
  ['design', 'Дизайн', ['designer', 'design_level', 'design_deadline']],
  ['docs', 'Договор', ['contract_no', 'adv', 'days', 'warranty']],
  ['pay', 'Оплата', []],
  ['work', 'В работе', ['curator', 'artists', 'start', 'end']],
]
const LABEL = { object: 'Объект', city: 'Город', service: 'Услуга', category: 'Категория', subcategory: 'Подкатегория', entry: 'Точка входа',
  address: 'Адрес объекта', area: 'Площадь, м²', adv: 'Аванс, %', days: 'Срок работ, календарных дней', warranty: 'Гарантия, месяцев',
  curator: 'Куратор ГИП', start: 'Старт работ (факт)', end: 'Сдача (план)', model: 'Модель', size: 'Размер проекта', vip: 'VIP-клиент',
  designer: 'Дизайнер', design_level: 'Сложность дизайна', design_deadline: 'Срок дизайна', contract_no: 'Номер договора', artists: 'Художники' }
const PROJ = ['category', 'subcategory', 'entry', 'model', 'size', 'vip', 'designer', 'design_level', 'design_deadline', 'contract_no', 'artists']
const CHIPS = ['model', 'size', 'design_level']
const LEVEL = { easy: 'Лёгкий', medium: 'Средний', hard: 'Сложный', author: 'Авторский' }
const fmt = v => v ? Number(v).toLocaleString('ru-RU').replace(/,/g, ' ') + ' ₸' : '—'
// то, что заполняется не здесь (клиент, расчёт, оплата), — видно в окне строками со своей кнопкой, чтобы карточка была целиком
function Info({ rows, children }) {
  return <div className="fillinfo" style={{ gridColumn: '1 / -1' }}>
    {rows.map(([k, v, bad]) => <div key={k} className="row"><span className="muted small">{k}</span><span className={bad ? 'why' : ''}>{v || '—'}</span></div>)}
    {children}
  </div>
}
export const subsOf = (cats, subs, catId) => {
  const i = (cats || []).findIndex(o => o.id === catId)
  return i < 0 ? [] : (subs || []).filter(o => (o.name || '').trim().startsWith(`${i + 1}.`))
}

export function FillSheet({ d, onClose, onDone, onClient, onCalc }) {
  const by = Object.fromEntries((d.fill?.items || []).map(x => [x.key, x]))
  const [f, setF] = useState({ object: d.object || '', cityName: d.city || '', city: '', service: '', area: d.area || '', address: d.address || '',
    adv: by.adv?.value || '', days: by.days?.value || '', warranty: by.warranty?.value || '', start: by.start?.value || '', end: by.end?.value || '' })
  const [pr, setPr] = useState(() => ({ ...(d.project || {}) }))
  const [ai, setAi] = useState({})          // какие поля подставил помощник
  const [dict, setDict] = useState({ cities: [], services: [], project: null })
  const [helper, setHelper] = useState(false)
  const [text, setText] = useState(() => { try { return localStorage.getItem(anketaKey(d.id)) || '' } catch { return '' } })
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  useEffect(() => { api('/bx/dict').then(x => { setDict(x); const s = x.services.find(s => s.name === d.service); setF(v => ({ ...v, service: s?.id || '' })) }, () => {}) }, [])
  // Куратор ГИП — человек приложения (objects.gip_person_id): только он даёт права ГИП (смены, люди, история объекта)
  const [gip, setGip] = useState({ id: '', was: '', list: null })
  useEffect(() => { api(`/bx/deals/${d.id}/gip`).then(r => setGip({ id: String(r.gip_id || ''), was: String(r.gip_id || ''), list: r.candidates }), () => setGip(g => ({ ...g, list: [] }))) }, [d.id])
  const have = k => k === 'curator' ? gip.list !== null : !PROJ.includes(k) || (dict.project?.have || []).includes(k)
  const need = k => by[k]?.need && !by[k]?.ok
  const set = (k, v) => { setF(x => ({ ...x, [k]: v })); setAi(a => ({ ...a, [k]: false })) }
  const parse = () => {
    setBusy('parse'); setMsg('')
    try { localStorage.setItem(anketaKey(d.id), text) } catch { /* без памяти */ }
    api(`/bx/deals/${d.id}/extract`, { method: 'POST', body: { text } }).then(r => {
      const x = r.fields, put = {}, mark = {}
      if (x.city) { put.city = x.city; put.cityName = x.cityName; mark.city = true }
      if (x.service) { put.service = x.service; mark.service = true }
      for (const k of ['area', 'address', 'adv', 'days', 'start']) if (x[k]) { put[k] = x[k]; mark[k] = true }
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
  for (const k of ['adv', 'days', 'warranty']) if (+f[k] && String(+f[k]) !== String(+by[k]?.value || '')) body[k] = +f[k]
  for (const k of ['start', 'end']) if (f[k] && f[k] !== (by[k]?.value || '')) body[k] = f[k]
  const p0 = d.project || {}
  const same = (a, b) => Array.isArray(a) || Array.isArray(b) ? [...(a || [])].sort().join() === [...(b || [])].sort().join() : String(a ?? '') === String(b ?? '')
  const prj = Object.fromEntries(PROJ.filter(k => have(k) && !same(pr[k], p0[k])).map(k => [k, k === 'vip' ? !!pr[k] : k === 'artists' ? pr[k] || [] : pr[k] || null]))
  if (Object.keys(prj).length) body.project = prj
  const gipNew = gip.id !== gip.was
  const n = Object.keys(body).length - (body.project ? 1 : 0) + Object.keys(prj).length + (gipNew ? 1 : 0)
  const save = async () => {
    setBusy('save')
    try {
      const r = Object.keys(body).length ? await api(`/bx/deals/${d.id}/fields`, { method: 'POST', body }) : null
      if (gipNew) await api(`/bx/deals/${d.id}/gip`, { method: 'POST', body: { person_id: +gip.id || 0 } })
      onDone(r?.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : r ? 'Карточка записана в Битрикс.' + (gipNew ? ' Куратор ГИП назначен.' : '') : 'Куратор ГИП назначен.')
    } catch (e) { setMsg('Не записалось: ' + e.message); setBusy('') }
  }

  const pd = dict.project || {}
  const subs = subsOf(pd.category, pd.subcategory, pr.category)
  const opts = { category: pd.category || [], subcategory: subs, entry: pd.entry || [], designer: pd.users || [] }
  const users = pd.users || []
  const setP = (k, v) => setPr(x => {
    const n = { ...x, [k]: v }
    if (k === 'category' && !subsOf(pd.category, pd.subcategory, v).some(o => o.id === x.subcategory)) n.subcategory = ''   // чужая подкатегория — сброс
    return n
  })
  const field = k => {
    if (k === 'curator') return <label key={k}><span>{LABEL[k]}</span><select value={gip.id} onChange={e => setGip(g => ({ ...g, id: e.target.value }))}>
      <option value="">—</option>{(gip.list || []).map(o => <option key={o.id} value={String(o.id)}>{o.full_name} · {o.role_title}</option>)}</select></label>
    const filled = PROJ.includes(k) ? pr[k] : k === 'city' ? (f.city || f.cityName) : f[k]
    const cls = (ai[k] ? 'ai ' : '') + (need(k) && !filled ? 'need' : '')
    const lab = <span>{LABEL[k]}{ai[k] && <i className="aitag">ИИ</i>}{need(k) && !filled && <i className="needtag">нужно</i>}</span>
    if (k === 'city') return <CityPicker key={k} cities={dict.cities} value={f.city || dict.cities.find(c => c.name === f.cityName)?.id || ''} need={need(k) && !filled}
      label="Город" onPick={(id, name) => { setF(x => ({ ...x, city: id, cityName: name })); setAi(a => ({ ...a, city: false })) }} />
    if (CHIPS.includes(k)) return <div key={k} className={'fillchips ' + cls}><span className="cplabel">{lab}</span><div className="chips">
      {(pd[k] || []).map(o => <button key={o.id} className={pr[k] === o.id ? 'on' : ''} onClick={() => setP(k, pr[k] === o.id ? '' : o.id)}>{o.name}</button>)}</div></div>
    if (k === 'vip') return <label key={k} className="check"><span>{LABEL[k]}</span><input type="checkbox" checked={!!pr.vip} onChange={e => setP('vip', e.target.checked)} /></label>
    if (k === 'design_deadline') return <label key={k} className={cls}>{lab}<input type="date" value={pr[k] || ''} onChange={e => setP(k, e.target.value)} /></label>
    if (k === 'contract_no') return <label key={k} className={cls}>{lab}<input value={pr[k] || ''} onChange={e => setP(k, e.target.value)} /></label>
    if (k === 'artists') {
      const a = pr.artists || [], uname = id => users.find(u => u.id === id)?.name || id
      return <div key={k} className="fillchips" style={{ gridColumn: '1 / -1' }}><span className="cplabel">{LABEL[k]}</span>
        <div className="chips">{a.map(id => <button key={id} className="on" onClick={() => setP('artists', a.filter(x => x !== id))}>{uname(id)} ✕</button>)}</div>
        <select value="" onChange={e => e.target.value && setP('artists', [...a, e.target.value])}><option value="">+ добавить художника</option>
          {users.filter(u => !a.includes(u.id)).map(u => <option key={u.id} value={u.id}>{u.name}{u.position ? ` · ${u.position}` : ''}</option>)}</select></div>
    }
    if (k === 'subcategory') return <label key={k} className={cls}>{lab}<select value={pr[k] || ''} disabled={!pr.category} onChange={e => setP(k, e.target.value)}>
      <option value="">{pr.category ? '—' : 'сначала категория'}</option>{subs.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
    if (PROJ.includes(k)) return <label key={k} className={cls}>{lab}<select value={pr[k] || ''} onChange={e => setP(k, e.target.value)}>
      <option value="">—</option>{opts[k].map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
    if (k === 'service') return <label key={k} className={cls}>{lab}<select value={f.service} onChange={e => set('service', e.target.value)}><option value="">—</option>{dict.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
    if (k === 'start' || k === 'end') return <label key={k} className={cls}>{lab}<input type="date" value={f[k]} onChange={e => set(k, e.target.value)} /></label>
    if (k === 'object') return <label key={k} className={cls} style={{ gridColumn: '1 / -1' }}>{lab}<input value={f.object} onChange={e => set('object', e.target.value)} placeholder="«Школа №12», «Кофейня Daily» — из него название сделки" /></label>
    if (k === 'address') return <label key={k} className={cls}>{lab}<input value={f.address} onChange={e => set('address', e.target.value)} placeholder="Улица, дом" /></label>
    return <label key={k} className={cls}>{lab}<input type="number" min="0" inputMode="decimal" value={f[k]} onChange={e => set(k, e.target.value)} /></label>
  }
  const miss = (d.fill?.items || []).filter(x => x.need && !x.ok)
  const c = d.client || {}
  return <Sheet title="Карточка сделки" onClose={onClose} wide>
    <div className="fillform">
      {miss.length ? <p className="small">Не хватает: <b>{miss.length}</b> — {miss.map(x => x.label).join(', ')}. В шагах ниже они отмечены «нужно».</p> : <p className="small ok">Всё нужное заполнено.</p>}
      <button className="ghost mini" onClick={() => setHelper(!helper)}>{helper ? 'Скрыть помощника' : 'Вставить переписку — помощник заполнит сам'}</button>
      {helper && <div className="aibox">
        <textarea rows={5} value={text} onChange={e => setText(e.target.value)} placeholder="Переписка из WhatsApp или анкета клиента: «нужна роспись в детском саду, Астана, Кенесары 40, примерно 45 м²…»" />
        <button className="mini" disabled={text.trim().length < 10 || !!busy} onClick={parse}>{busy === 'parse' ? 'Разбираю…' : 'Разобрать'}</button>
      </div>}
      {msg && <p className="small">{msg}</p>}
      {SECTIONS.map(([step, title, keys]) => {
        const ks = keys.filter(have).sort((a, b) => (need(b) ? 1 : 0) - (need(a) ? 1 : 0))
        const ro = step === 'client' ? ['name', 'phone', 'requisites'] : step === 'calc' ? ['sum', 'calc', 'kp'] : step === 'pay' ? ['paid', 'signed'] : []
        const nn = ks.filter(need).length + ro.filter(need).length
        return <div key={step} className="fillgrid">
          <h3 className="fillsec">{title}{nn ? <i className="needtag">нужно {nn}</i> : null}</h3>
          {step === 'client' && <Info rows={[['Клиент', c.name ? (c.type && !c.name.startsWith(c.type) ? `${c.type} · ${c.name}` : c.name) : '', need('name')], ['Телефон', c.phone, need('phone')],
            ['БИН / ИИН', c.type === 'Физлицо' ? 'не нужен' : d.requisites?.cbin, need('requisites')]]}>
            {onClient && <button className="ghost mini" onClick={onClient}>Клиент и реквизиты</button>}</Info>}
          {step === 'calc' && <Info rows={[['Сумма сделки', d.sum ? fmt(d.sum) : '', need('sum')], ['Сложность', LEVEL[d.level] || ''],
            ['Смен / художников по норме', d.norm?.shifts ? `${d.norm.shifts} / ${d.norm.crew || '—'}` : '', need('calc')], ['Срок, рабочих дней', d.norm?.term || ''],
            ['КП в сделке', by.kp?.ok ? 'есть' : 'нет', need('kp')]]}>
            {onCalc && <button className="ghost mini" onClick={onCalc}>{d.sum ? 'Пересчитать цену и срок' : 'Посчитать цену и срок'}</button>}</Info>}
          {step === 'pay' && <Info rows={[['Поступило', fmt(d.pay?.received), need('paid')], ['Долг', d.pay?.debt ? fmt(d.pay.debt) : '0 ₸'],
            ['Подписанный договор', by.signed?.ok ? 'есть' : 'нет', need('signed')]]} />}
          {ks.map(field)}
        </div>
      })}
      <button disabled={!n || !!busy} onClick={save}>{busy === 'save' ? 'Записываю…' : `Записать в Битрикс${n ? ` (${n})` : ''}`}</button>
    </div>
  </Sheet>
}

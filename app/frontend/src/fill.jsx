import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Copy, Sheet } from './ui.jsx'

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
  </div>
}

const EDIT = [['city', 'Город'], ['service', 'Услуга'], ['area', 'Площадь, м²'], ['address', 'Адрес объекта'],
  ['adv', 'Аванс, %'], ['days', 'Срок по договору, календарных дней'], ['warranty', 'Гарантия, месяцев'], ['start', 'Старт работ (факт)'], ['end', 'Сдача (план)']]

export function FillSheet({ d, onClose, onDone }) {
  const by = Object.fromEntries((d.fill?.items || []).map(x => [x.key, x]))
  const init = { cityName: d.city || '', city: '', service: '', area: d.area || '', address: d.address || '',
    adv: by.adv?.value || '', days: by.days?.value || '', warranty: by.warranty?.value || '', start: by.start?.value || '', end: by.end?.value || '' }
  const [f, setF] = useState(init)
  const [ai, setAi] = useState({})          // какие поля подставил помощник
  const [dict, setDict] = useState({ cities: [], services: [] })
  const [text, setText] = useState(() => { try { return localStorage.getItem(anketaKey(d.id)) || '' } catch { return '' } })
  const [found, setFound] = useState(null)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState('')
  useEffect(() => { api('/bx/dict').then(x => { setDict(x); const s = x.services.find(s => s.name === d.service); setF(v => ({ ...v, service: s?.id || '' })) }, () => {}) }, [])
  const set = (k, v) => { setF(x => ({ ...x, [k]: v })); setAi(a => ({ ...a, [k]: false })) }
  const pickCity = v => { const c = dict.cities.find(x => x.name.toLowerCase() === v.trim().toLowerCase()); setF(x => ({ ...x, cityName: v, city: c ? c.id : '' })); setAi(a => ({ ...a, city: false })) }
  const parse = () => {
    setBusy('parse'); setMsg('')
    try { localStorage.setItem(anketaKey(d.id), text) } catch { /* без памяти */ }
    api(`/bx/deals/${d.id}/extract`, { method: 'POST', body: { text } }).then(r => {
      const x = r.fields, put = {}, mark = {}
      if (x.city) { put.city = x.city; put.cityName = x.cityName; mark.city = true }
      if (x.service) { put.service = x.service; mark.service = true }
      for (const k of ['area', 'address', 'adv', 'days', 'start']) if (x[k]) { put[k] = x[k]; mark[k] = true }
      setF(v => ({ ...v, ...put })); setAi(mark); setFound(r)
      setMsg((r.source === 'ai' ? 'ИИ разобрал текст' : 'Разобрал по правилам') + (r.note ? ` (${r.note})` : '') + `: подставлено ${Object.keys(mark).length} полей. Проверьте и запишите.`)
    }, e => setMsg(e.message)).finally(() => setBusy(''))
  }
  const body = {}
  if (f.city && f.cityName !== d.city) body.city = f.city
  if (f.service && (dict.services.find(s => s.id === f.service)?.name || '') !== (d.service || '')) body.service = f.service
  if (+f.area && +f.area !== (d.area || 0)) body.area = +f.area
  if (f.address && f.address !== (d.address || '')) body.address = f.address
  for (const k of ['adv', 'days', 'warranty']) if (+f[k] && String(+f[k]) !== String(+by[k]?.value || '')) body[k] = +f[k]
  for (const k of ['start', 'end']) if (f[k] && f[k] !== (by[k]?.value || '')) body[k] = f[k]
  const save = () => { setBusy('save'); api(`/bx/deals/${d.id}/fields`, { method: 'POST', body })
    .then(r => onDone(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Карточка записана в Битрикс.'), e => { setMsg('Не записалось: ' + e.message); setBusy('') }) }
  const need = k => by[k] && by[k].need && !by[k].ok
  const cls = k => (ai[k] ? 'ai ' : '') + (need(k) ? 'need' : '')
  const field = (k, label) => {
    const lab = <span>{label}{ai[k] && <i className="aitag">ИИ</i>}{need(k) && !f[k] && <i className="needtag">нужно</i>}</span>
    if (k === 'city') return <label key={k} className={cls(k)}>{lab}<input list="fill-cities" value={f.cityName} onChange={e => pickCity(e.target.value)} placeholder="Начните вводить" /></label>
    if (k === 'service') return <label key={k} className={cls(k)}>{lab}<select value={f.service} onChange={e => set('service', e.target.value)}><option value="">—</option>{dict.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
    if (k === 'start' || k === 'end') return <label key={k} className={cls(k)}>{lab}<input type="date" value={f[k]} onChange={e => set(k, e.target.value)} /></label>
    if (k === 'address') return <label key={k} className={cls(k)}>{lab}<input value={f[k]} onChange={e => set(k, e.target.value)} placeholder="Город, улица, дом" /></label>
    return <label key={k} className={cls(k)}>{lab}<input type="number" min="0" inputMode="decimal" value={f[k]} onChange={e => set(k, e.target.value)} /></label>
  }
  const other = (d.fill?.items || []).filter(x => !x.edit && !x.ok && x.need)
  const cl = found?.client || {}
  const clRows = [['Клиент', cl.name], ['Юрлицо', cl.company], ['БИН/ИИН', cl.bin], ['Подписант', cl.signer], ['Телефон', cl.phone], ['E-mail', cl.email], ['Пожелания', cl.wishes]].filter(x => x[1])
  return <Sheet title="Заполнить карточку" onClose={onClose} wide>
    <div className="aibox">
      <div className="aihead"><b>Помощник</b><span className="small">вставьте переписку из WhatsApp или анкету клиента — поля заполнятся сами</span></div>
      <textarea rows={5} value={text} onChange={e => setText(e.target.value)} placeholder="Например: «Здравствуйте, нужна роспись в детском саду, Астана, ул. Кенесары 40, примерно 45 м²…»" />
      <button className="mini" disabled={text.trim().length < 10 || !!busy} onClick={parse}>{busy === 'parse' ? 'Разбираю…' : 'Разобрать'}</button>
      {msg && <p className="small">{msg}</p>}
      {!!clRows.length && <div className="found">
        {clRows.map(([k, v]) => <div key={k} className="row"><span className="muted small">{k}</span><span>{v}</span></div>)}
        <p className="small muted">Реквизиты и подписант уйдут в договор сами: этот же текст подставится в «Договор → Заполнить из текста». Телефон и имя клиента правьте в карточке клиента в Битриксе.</p>
        <Copy text={clRows.map(([k, v]) => `${k}: ${v}`).join('\n')} label="Скопировать данные клиента" />
      </div>}
    </div>
    <datalist id="fill-cities">{dict.cities.map(c => <option key={c.id} value={c.name} />)}</datalist>
    <div className="fillgrid">{EDIT.map(([k, l]) => field(k, l))}</div>
    {!!other.length && <div className="fillother"><b className="small">Ещё не хватает</b>
      {other.map(x => <div key={x.key} className="row"><span>{x.label}</span><span className="muted small">{x.where}</span></div>)}</div>}
    <button disabled={!Object.keys(body).length || !!busy} onClick={save}>{busy === 'save' ? 'Записываю…' : `Записать в Битрикс${Object.keys(body).length ? ` (${Object.keys(body).length})` : ''}`}</button>
  </Sheet>
}

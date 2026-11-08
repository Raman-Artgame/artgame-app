import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { clearFailed, enqueue, failed, flush, pending } from './queue.js'

const ZONE = { mural: 'Роспись', print: 'Печать', design: 'Дизайн', sales: 'Продажи' }
const ST = { open: 'идёт', submitted: 'на проверке', approved: 'принято', rejected: 'отказ', cancelled: 'отменено' }
const local = d => { const x = new Date(d); x.setMinutes(x.getMinutes() - x.getTimezoneOffset()); return x.toISOString().slice(0, 16) }
const iso = v => new Date(v).toISOString()
const money = n => Number(n).toLocaleString('ru-RU') + ' ₸'

// Чек сжимаем на телефоне (до 1600 px, JPEG): быстрее уходит при плохой сети и помещается в офлайн-очередь.
export function shrink(file) {
  return new Promise((ok, fail) => {
    const img = new Image()
    img.onload = () => {
      const k = Math.min(1, 1600 / Math.max(img.width, img.height))
      const c = document.createElement('canvas'); c.width = img.width * k; c.height = img.height * k
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
      URL.revokeObjectURL(img.src); ok(c.toDataURL('image/jpeg', 0.75))
    }
    img.onerror = fail
    img.src = URL.createObjectURL(file)
  })
}

function useDict() {
  const [d, setD] = useState(null)
  useEffect(() => { api('/work/dict').then(d => { setD(d); localStorage.setItem('artgame.dict', JSON.stringify(d)) },
    () => setD(JSON.parse(localStorage.getItem('artgame.dict') || 'null'))) }, [])
  return d
}

function Common({ d, v, set }) {
  return <>
    <label className="muted">Объект</label>
    <select value={v.object_id} onChange={e => set({ ...v, object_id: +e.target.value })}>
      {d.objects.map(o => <option key={o.id} value={o.id}>{o.id ? `№${o.id} · ` : ''}{o.title}{o.city ? ` — ${o.city}` : ''}</option>)}
    </select>
    {d.zones.length > 1 && <>
      <label className="muted">Зона</label>
      <select value={v.zone_code} onChange={e => set({ ...v, zone_code: e.target.value })}>
        {d.zones.map(z => <option key={z} value={z}>{ZONE[z]}</option>)}
      </select></>}
  </>
}

const CX = [['easy', 'Лёгкий'], ['medium', 'Средний'], ['hard', 'Сложный'], ['author', 'Авторский']]
const pct = k => Math.round(k * 100) + '%'
// «7 нояб., 09:00–18:00» — без секунд, с концом смены
export const when = (a, b) => new Date(a).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) +
  (b ? '–' + new Date(b).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '')
const m2 = x => Number(x).toLocaleString('ru-RU', { maximumFractionDigits: 2 })


const LKEY = 'artgame.shift.open'
const loadOpen = () => { try { return JSON.parse(localStorage.getItem(LKEY) || 'null') } catch { return null } }
const saveOpen = v => { try { v ? localStorage.setItem(LKEY, JSON.stringify(v)) : localStorage.removeItem(LKEY) } catch { /* без памяти */ } }
const hm = ms => { const m = Math.max(0, Math.floor(ms / 60000)); return `${Math.floor(m / 60)} ч ${String(m % 60).padStart(2, '0')} мин` }
const LV = Object.fromEntries(CX)

// Промо объекта (HEAD 08.11): что предстоит — условия из сделки (заполняет МОП, здесь без выбора), норма на смену, эскизы.
export function Promo({ id, zone, compact }) {
  const [c, setC] = useState(null)
  useEffect(() => { if (id) api(`/work/object/${id}?zone=${zone || 'mural'}`).then(setC, () => setC(null)) }, [id, zone])
  if (!id || !c) return null
  const conds = [['at_height', 'На высоте'], ['outdoor', 'Улица'], ['hard_surface', 'Сложная поверхность']]
  return <div className="card dark promo">
    <div className="promo-top"><span className="kick">Что предстоит</span>{c.now.length > 0 && <span className="small muted">сейчас на объекте: {c.now.map(n => n.split(' ')[0]).join(', ')}</span>}</div>
    {!compact && <h2>{c.title}</h2>}
    <p className="small muted">{[c.city, c.address, c.area ? `${m2(c.area)} м²` : ''].filter(Boolean).join(' · ') || 'адрес не указан в сделке'}</p>
    {zone !== 'print' && <>
      <div className="promo-lvl"><span>Сложность</span><b>{c.complexity ? LV[c.complexity] : 'МОП ещё не указал'}</b></div>
      <div className="conds">{conds.map(([k, t]) => <span key={k} className={c[k] ? 'on' : ''}>{c[k] ? '● ' : ''}{t}</span>)}</div></>}
    {c.plan_m2 ? <p className="small">Норма на твою смену — <b>{m2(c.plan_m2)} м²</b></p> : null}
    {c.sketches.length > 0 && <div className="sketches">{c.sketches.map(f => <a key={f.id} href={f.url} target="_blank" rel="noreferrer"><img src={f.thumb} alt={f.name} loading="lazy" /></a>)}</div>}
    <p className="small muted">Условия заполняет МОП в карточке сделки. Не так на объекте — скажи Главному художнику.</p>
  </div>
}

function Snap({ value, set, label }) {
  return <label className={'photo snap' + (value ? ' has' : '')}>
    {value ? <img src={value} alt={label} /> : <span>📷 {label}</span>}
    <input type="file" accept="image/*" capture="environment" hidden onChange={async e => e.target.files[0] && set(await shrink(e.target.files[0]))} />
  </label>
}

// Смена по шагам (HEAD 08.11): «Начать» с фото стены до → смена идёт → «Закончить» с фото в конце, м² и «что сделал».
export function ShiftForm({ done }) {
  const d = useDict()
  const [open, setOpen] = useState(loadOpen)
  const [checked, setChecked] = useState(false)
  useEffect(() => {
    api('/shifts/open').then(r => {
      if (r.shift) { const o = { client_uid: r.shift.client_uid, object_id: r.shift.object_id, object_title: r.shift.object_title,
        zone_code: r.shift.zone_code, started_at: r.shift.started_at, before: r.shift.photo_before_url }; saveOpen(o); setOpen(o) }
      else if (!pending()) { saveOpen(null); setOpen(null) }   // закрыта на сервере, а в очереди ничего нет
    }, () => {}).finally(() => setChecked(true))
  }, [])
  if (!d) return <div className="card muted">Загрузка…</div>
  if (open) return <Running o={open} d={d} done={t => { saveOpen(null); setOpen(null); done(t) }} />
  return <StartShift d={d} checked={checked} onStarted={o => { saveOpen(o); setOpen(o) }} />
}

function StartShift({ d, onStarted }) {
  const objs = d.objects.filter(o => o.id)
  const [v, set] = useState({ object_id: objs[0]?.id, zone_code: d.zones[0] })
  const [photo, setPhoto] = useState('')
  const [busy, setBusy] = useState(false)
  if (!objs.length) return <div className="card"><h2>Смена</h2><p className="muted">Сейчас нет объектов в работе. Когда МОП переведёт сделку в «Выполнение проекта», объект появится здесь.</p></div>
  const obj = objs.find(o => o.id === v.object_id) || objs[0]
  const start = async () => {
    setBusy(true)
    const geo = await new Promise(r => navigator.geolocation ? navigator.geolocation.getCurrentPosition(p => r(p.coords), () => r(null), { timeout: 4000 }) : r(null))
    const o = { client_uid: crypto.randomUUID(), object_id: obj.id, object_title: obj.title, zone_code: v.zone_code, started_at: new Date().toISOString(), before: photo }
    try {
      await enqueue('/shifts/start', { client_uid: o.client_uid, object_id: o.object_id, zone_code: o.zone_code, started_at: o.started_at, photo_before: photo,
        geo_lat: geo?.latitude ?? null, geo_lon: geo?.longitude ?? null })
      onStarted(o)
    } catch { /* режим просмотра */ } finally { setBusy(false) }
  }
  return <>
    <div className="card">
      <div className="steps"><span className="on">1 Начало</span><span>2 Работа</span><span>3 Конец смены</span></div>
      <h2>Начать смену</h2>
      <label className="muted">Объект</label>
      <div className="objpick">{objs.map(o => <button key={o.id} className={o.id === obj.id ? 'on' : ''} onClick={() => set({ ...v, object_id: o.id })}>
        <b>№{o.id}</b> {o.title}{o.city ? <span> · {o.city}</span> : null}</button>)}</div>
      {d.zones.length > 1 && <div className="segf">{d.zones.map(z => <button key={z} className={v.zone_code === z ? 'on' : ''} onClick={() => set({ ...v, zone_code: z })}>{ZONE[z]}</button>)}</div>}
    </div>
    <Promo id={obj.id} zone={v.zone_code} compact={false} />
    <div className="card">
      <h3>Фото стены до начала</h3>
      <Snap value={photo} set={setPhoto} label="Сфотографировать стену" />
      <button disabled={!photo || busy} onClick={start}>{busy ? 'Начинаю…' : 'Начать смену'}</button>
      {!photo && <p className="small muted">Без фото «до» смену не начать: по нему Главный художник видит, что сделано за день.</p>}
    </div>
  </>
}

function Running({ o, d, done }) {
  const [now, setNow] = useState(Date.now())
  const [v, set] = useState({ area_m2: '', work_done: '', note: '', printer: d.printer || '' })
  const [photo, setPhoto] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t) }, [])
  const print = o.zone_code === 'print'
  const ok = photo && v.work_done.trim().length >= 3
  const finish = async () => {
    setBusy(true)
    try {
      const left = await enqueue('/shifts/finish', { client_uid: o.client_uid, ended_at: new Date().toISOString(), area_m2: v.area_m2 === '' ? null : +v.area_m2,
        work_done: v.work_done.trim(), photo_after: photo, note: v.note || null, printer: print ? v.printer || null : null })
      done(left ? 'Сохранено на телефоне, отправится, когда будет сеть.' : 'Смена закончена и ушла на проверку.')
    } catch { setBusy(false) }
  }
  const cancel = () => { if (confirm('Отменить смену? Она не уйдёт на проверку.')) api('/shifts/open').then(r => r.shift && api(`/shift/${r.shift.id}/cancel`, { method: 'POST' })).finally(() => done('Смена отменена.')) }
  return <>
    <div className="card dark live">
      <div className="steps dark"><span className="done">1 Начало</span><span className="on">2 Работа</span><span>3 Конец смены</span></div>
      <span className="kick">Смена идёт</span>
      <div className="timer">{hm(now - new Date(o.started_at).getTime())}</div>
      <p className="small muted">с {new Date(o.started_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })} · №{o.object_id} {o.object_title} · {ZONE[o.zone_code]}</p>
      {o.before && <img className="before" src={o.before} alt="стена до" />}
    </div>
    <Promo id={o.object_id} zone={o.zone_code} compact />
    <div className="card">
      <h2>Закончить смену</h2>
      <label className="muted">{print ? 'Напечатано, м²' : 'Сделано, м²'}</label>
      <input inputMode="decimal" value={v.area_m2} onChange={e => set({ ...v, area_m2: e.target.value.replace(',', '.') })} placeholder="например, 4,5" />
      <label className="muted">Что сделал за смену</label>
      <textarea rows="3" value={v.work_done} onChange={e => set({ ...v, work_done: e.target.value })} placeholder="Например: загрунтовал стену, перенёс эскиз, прописал фон слева" />
      {print && <><label className="muted">Принтер</label><input value={v.printer} onChange={e => set({ ...v, printer: e.target.value })} placeholder="Название принтера" /></>}
      <input placeholder="Комментарий (по желанию)" value={v.note} onChange={e => set({ ...v, note: e.target.value })} />
      <h3>Фото в конце смены</h3>
      <Snap value={photo} set={setPhoto} label="Сфотографировать результат" />
      <button disabled={!ok || busy} onClick={finish}>{busy ? 'Отправляю…' : 'Закончить и отправить на проверку'}</button>
      {!ok && <p className="small muted">Нужно фото в конце смены и пара слов, что сделано.</p>}
      <p className="small"><a onClick={cancel}>Отменить смену</a></p>
    </div>
  </>
}

export function ExpenseForm({ done }) {
  const d = useDict()
  const [v, set] = useState(null)
  useEffect(() => { if (d) set({ object_id: d.objects[0]?.id, zone_code: d.zones[0], category: d.categories[0]?.code, amount: '', paid_by: 'own', note: '' }) }, [d])
  if (!d || !v) return <div className="card muted">Загрузка…</div>
  const send = async () => {
    const left = await enqueue('/expenses', { ...v, amount: +v.amount })
    done(left ? 'Сохранено на телефоне, отправится, когда будет сеть.' : 'Расход отправлен на проверку.')
  }
  return <div className="card">
    <h2>Расход</h2>
    <Common d={d} v={v} set={set} />
    <label className="muted">Категория</label>
    <select value={v.category} onChange={e => set({ ...v, category: e.target.value })}>
      {d.categories.map(c => <option key={c.code} value={c.code}>{c.title}</option>)}
    </select>
    <label className="muted">Сумма, ₸</label><input inputMode="numeric" value={v.amount} onChange={e => set({ ...v, amount: e.target.value.replace(/\D/g, '') })} />
    <div className="seg">
      <button className={v.paid_by === 'own' ? '' : 'ghost'} onClick={() => set({ ...v, paid_by: 'own' })}>Свои деньги</button>
      <button className={v.paid_by === 'company' ? '' : 'ghost'} onClick={() => set({ ...v, paid_by: 'company' })}>Компании</button>
    </div>
    <input placeholder="Комментарий" value={v.note} onChange={e => set({ ...v, note: e.target.value })} />
    <label className="photo">
      {v.receipt ? <img src={v.receipt} alt="чек" /> : <span>📷 Фото чека</span>}
      <input type="file" accept="image/*" capture="environment" hidden onChange={async e => e.target.files[0] && set({ ...v, receipt: await shrink(e.target.files[0]) })} />
    </label>
    <button disabled={!v.amount} onClick={send}>Отправить расход</button>
  </div>
}

export function Mine() {
  const [m, setM] = useState(null)
  const load = () => api('/my').then(setM, () => {})
  useEffect(() => {
    flush(); load()
    window.addEventListener('artgame:queue', load)
    return () => window.removeEventListener('artgame:queue', load)
  }, [])
  if (!m) return <div className="card muted">Загрузка…</div>
  const cancel = (k, id) => api(`/${k}/${id}/cancel`, { method: 'POST' }).then(load)
  return <>
    {pending() > 0 && <div className="card">Ждут сети: {pending()}</div>}
    {failed().length > 0 && <div className="card"><h3>Не принято сервером</h3>
      {failed().map((x, i) => <div key={i} className="row"><div><b>{x.amount ? money(x.amount) : x.path}</b>{x.note ? ` · ${x.note}` : ''}
        <div className="small why">{x.error}</div></div></div>)}
      <button className="ghost mini" onClick={() => { clearFailed(); load() }}>Понятно, скрыть</button></div>}
    <div className="card"><h2>Мои смены</h2>
      {m.shifts.length ? m.shifts.map(s => <div key={s.id} className="row">
        <div><b>{s.object_title}</b><br /><span className="muted small">{when(s.started_at, s.ended_at)}{s.area_m2 ? ` · ${+s.area_m2} м²` : ''}</span>
          {s.plan_m2 && <div className="small">{s.zone_code === 'print' ? 'План' : 'Норма'} {m2(s.plan_m2)} м²{s.kpd != null && <> · КПД <b>{pct(s.kpd)}</b></>}{+s.bonus > 0 && <> · бонус <b>{money(s.bonus)}</b></>}</div>}
          {s.work_done && <div className="small">Сделал: {s.work_done}</div>}
          {(s.photo_before_url || s.photo_after_url) && <div className="pair">{s.photo_before_url && <img src={s.photo_before_url} alt="до" />}{s.photo_after_url && <img src={s.photo_after_url} alt="после" />}</div>}
          {s.reason && <div className="small">Причина: {s.reason}</div>}</div>
        <span className={`tag st-${s.status}`}>{ST[s.status]}</span>
        {s.status === 'submitted' && <a onClick={() => cancel('shift', s.id)}>отменить</a>}
      </div>) : <p className="muted">Пока нет</p>}
    </div>
    <div className="card"><h2>Мои расходы</h2>
      {m.expenses.length ? m.expenses.map(e => <div key={e.id} className="row">
        <div><b>{money(e.amount)}</b> · {e.object_title}<br /><span className="muted small">{e.payout_status === 'to_pay' ? 'к выплате' : e.payout_status === 'paid' ? 'выплачено' : ''}</span>
          {e.receipt_url && <a href={e.receipt_url} target="_blank" rel="noreferrer"> чек</a>}
          {e.reason && <div className="small">Причина: {e.reason}</div>}</div>
        <span className={`tag st-${e.status}`}>{ST[e.status]}</span>
        {e.status === 'submitted' && <a onClick={() => cancel('expense', e.id)}>отменить</a>}
      </div>) : <p className="muted">Пока нет</p>}
    </div>
  </>
}

export function Review() {
  const [r, setR] = useState(null)
  const load = () => api('/review').then(setR, () => setR({ shifts: [], expenses: [] }))
  useEffect(() => { load() }, [])
  if (!r) return <div className="card muted">Загрузка…</div>
  const decide = (k, id, approve) => {
    const reason = approve ? null : prompt('Причина отказа')
    if (!approve && !reason) return
    api(`/${k}/${id}/review`, { method: 'POST', body: { approve, reason } }).then(load)
  }
  const Item = ({ k, x, children }) => <div className="row">
    <div><b>{x.person_name}</b> · {x.object_title}<br /><span className="muted small">{children}</span>
      {x.work_done && <div className="small">Сделал: {x.work_done}</div>}
      {(x.photo_before_url || x.photo_after_url) && <div className="pair">{x.photo_before_url && <a href={x.photo_before_full} target="_blank" rel="noreferrer"><img src={x.photo_before_url} alt="до" /></a>}
        {x.photo_after_url && <a href={x.photo_after_full} target="_blank" rel="noreferrer"><img src={x.photo_after_url} alt="после" /></a>}</div>}</div>
    <div className="seg"><button onClick={() => decide(k, x.id, true)}>✓</button><button className="ghost" onClick={() => decide(k, x.id, false)}>✕</button></div>
  </div>
  return <>
    <div className="card"><h2>Смены на проверку</h2>
      {r.shifts.length ? r.shifts.map(x => <Item key={x.id} k="shift" x={x}>{when(x.started_at, x.ended_at)}{x.area_m2 ? ` · ${+x.area_m2} м²` : ''} · {ZONE[x.zone_code]}{x.plan_m2 ? ` · ${x.zone_code === 'print' ? 'план' : 'норма'} ${m2(x.plan_m2)} м²` : ''}{x.kpd != null ? ` · КПД ${pct(x.kpd)}` : ''}{x.printer ? ` · ${x.printer}` : ''}</Item>) : <p className="muted">Всё проверено</p>}
    </div>
    <div className="card"><h2>Расходы на проверку</h2>
      {r.expenses.length ? r.expenses.map(x => <Item key={x.id} k="expense" x={x}>{money(x.amount)} · {x.paid_by === 'own' ? 'свои' : 'компании'}{x.note ? ' · ' + x.note : ''}{x.receipt_url ? <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></> : ' · без чека'}</Item>) : <p className="muted">Всё проверено</p>}
    </div>
  </>
}

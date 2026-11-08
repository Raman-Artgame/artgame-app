import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { enqueue, flush, pending } from './queue.js'

const ZONE = { mural: 'Роспись', print: 'Печать', design: 'Дизайн', sales: 'Продажи' }
const ST = { submitted: 'на проверке', approved: 'принято', rejected: 'отказ', cancelled: 'отменено' }
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

function Check({ v, set, k, t }) {
  return <label className="check"><input type="checkbox" checked={!!v[k]} onChange={e => set({ ...v, [k]: e.target.checked })} /> {t}</label>
}

export function ShiftForm({ done }) {
  const d = useDict()
  const [v, set] = useState(null)
  useEffect(() => { if (d) set({ object_id: d.objects[0]?.id, zone_code: d.zones[0], started_at: local(Date.now() - 9 * 3600e3), ended_at: local(Date.now()), area_m2: '', note: '',
    complexity: 'medium', printer: d.printer || '', at_height: false, outdoor: false, hard_surface: false }) }, [d])
  if (!d || !v) return <div className="card muted">Загрузка…</div>
  const send = async () => {
    const geo = await new Promise(r => navigator.geolocation ? navigator.geolocation.getCurrentPosition(p => r(p.coords), () => r(null), { timeout: 4000 }) : r(null))
    const mural = v.zone_code === 'mural', print = v.zone_code === 'print'
    const left = await enqueue('/shifts', { ...v, complexity: mural ? v.complexity : null, printer: print ? v.printer || null : null,
      at_height: mural && v.at_height, outdoor: mural && v.outdoor, hard_surface: mural && v.hard_surface, started_at: iso(v.started_at), ended_at: iso(v.ended_at), area_m2: v.area_m2 === '' ? null : +v.area_m2,
      geo_lat: geo?.latitude ?? null, geo_lon: geo?.longitude ?? null })
    done(left ? 'Сохранено на телефоне, отправится, когда будет сеть.' : 'Смена отправлена на проверку.')
  }
  return <div className="card">
    <h2>Смена</h2>
    <Common d={d} v={v} set={set} />
    <label className="muted">Начало</label><input type="datetime-local" value={v.started_at} onChange={e => set({ ...v, started_at: e.target.value })} />
    <label className="muted">Конец</label><input type="datetime-local" value={v.ended_at} onChange={e => set({ ...v, ended_at: e.target.value })} />
    <label className="muted">{v.zone_code === 'print' ? 'Напечатано, м²' : 'Сделано, м²'}</label>
    <input inputMode="decimal" value={v.area_m2} onChange={e => set({ ...v, area_m2: e.target.value.replace(',', '.') })} />
    {v.zone_code === 'mural' && <>
      <label className="muted">Сложность росписи</label>
      <div className="seg grid2">{CX.map(([k, t]) => <button key={k} className={v.complexity === k ? '' : 'ghost'} onClick={() => set({ ...v, complexity: k })}>{t}</button>)}</div>
      <Check v={v} set={set} k="at_height" t="На высоте" />
      <Check v={v} set={set} k="outdoor" t="Улица" />
      <Check v={v} set={set} k="hard_surface" t="Сложная поверхность" />
    </>}
    {v.zone_code === 'print' && <><label className="muted">Принтер</label>
      <input value={v.printer} onChange={e => set({ ...v, printer: e.target.value })} placeholder="Название принтера" /></>}
    <input placeholder="Комментарий" value={v.note} onChange={e => set({ ...v, note: e.target.value })} />
    <button onClick={send}>Отправить смену</button>
  </div>
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
    <div className="card"><h2>Мои смены</h2>
      {m.shifts.length ? m.shifts.map(s => <div key={s.id} className="row">
        <div><b>{s.object_title}</b><br /><span className="muted small">{when(s.started_at, s.ended_at)}{s.area_m2 ? ` · ${+s.area_m2} м²` : ''}</span>
          {s.plan_m2 && <div className="small">{s.zone_code === 'print' ? 'План' : 'Норма'} {m2(s.plan_m2)} м²{s.kpd != null && <> · КПД <b>{pct(s.kpd)}</b></>}{+s.bonus > 0 && <> · бонус <b>{money(s.bonus)}</b></>}</div>}
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
    <div><b>{x.person_name}</b> · {x.object_title}<br /><span className="muted small">{children}</span></div>
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

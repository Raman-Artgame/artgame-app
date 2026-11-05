import React, { useEffect, useState } from 'react'
import { api } from './api.js'

export const DEAL_ROLES = new Set(['mop', 'mop_vip', 'head'])
const money = n => n ? Math.round(n).toLocaleString('ru-RU') + ' ₸' : '—'
const when = s => s ? new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : ''

// Мои открытые сделки из Битрикса (ответственный — я; HEAD видит всех). Только чтение.
// «КП» / «Документы» открывают место МОП, и страница сама подтягивает сделку.
export function Deals({ me, openPlace }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const load = fresh => { setBusy(true); setErr(''); return api(`/bx/deals${fresh ? '?fresh=1' : ''}`).then(setData, e => setErr(e.message)).finally(() => setBusy(false)) }
  useEffect(() => { load(false) }, [])
  const open = (id, view) => {
    try { localStorage.setItem('artgame.bx.open', JSON.stringify({ id, view, t: Date.now() })); localStorage.setItem('artgame.place', 'mop') } catch { /* без памяти */ }
    openPlace()
  }
  if (err) return <div className="card"><h2>Мои сделки</h2><p className="muted">{err}</p></div>
  if (!data) return <div className="card muted">Загружаю сделки из Битрикса…</div>
  const s = q.trim().toLowerCase()
  const list = data.deals.filter(d => !s || String(d.id).includes(s) || d.title.toLowerCase().includes(s) || (d.manager || '').toLowerCase().includes(s))
  const groups = {}
  list.forEach(d => { (groups[d.stage_name] ||= { sort: d.stage_sort + d.category * 1000, items: [] }).items.push(d) })
  return <div className="card"><h2>{data.all ? 'Сделки в работе' : 'Мои сделки'} <span className="muted small">{data.deals.length}</span></h2>
    <div className="dealbar"><input value={q} onChange={e => setQ(e.target.value)} placeholder="Номер, название или менеджер" />
      <button className="ghost" disabled={busy} onClick={() => load(true)}>{busy ? '…' : 'Обновить'}</button></div>
    {!list.length && <p className="muted">Открытых сделок нет.</p>}
    {Object.entries(groups).sort((a, b) => a[1].sort - b[1].sort).map(([name, g]) => <div key={name}>
      <div className="dealstage">{name} <span className="muted">· {g.items.length}</span></div>
      {g.items.map(d => <div key={d.id} className="deal">
        <div><b>№ {d.id}</b> {d.title.replace(new RegExp(`^№?\\s*${d.id}\\s*·?\\s*`), '')}</div>
        <div className="muted small">{[d.city, d.area ? d.area + ' м²' : '', money(d.sum), d.manager, when(d.modified)].filter(Boolean).join(' · ')}</div>
        <div className="dealbtns"><button className="ghost" onClick={() => open(d.id, 'kp')}>КП</button>
          <button className="ghost" onClick={() => open(d.id, 'docs')}>Документы</button></div>
      </div>)}
    </div>)}
  </div>
}

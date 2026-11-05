import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { DealCard } from './dealcard.jsx'
import { MonthStrip, ageDays, cleanTitle, money } from './crm.jsx'

export const DEAL_ROLES = new Set(['mop', 'mop_vip', 'head'])
const IDLE = 3   // дней без движения — красный бейдж (как mop.today.idle_days)

// Сделки воронкой: стадии свёрнутыми группами с количеством и суммой, внутри — дни без движения.
// Действия (стадия, заметка, звонок, расчёт, КП) — в карточке сделки.
export function Deals({ initial, openPlace, openMonth }) {
  const [card, setCard] = useState(initial || null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [openSt, setOpenSt] = useState({})
  const load = fresh => { setBusy(true); setErr(''); return api(`/bx/deals${fresh ? '?fresh=1' : ''}`).then(setData, e => setErr(e.message)).finally(() => setBusy(false)) }
  useEffect(() => { load(false) }, [])
  const open = (id, view) => {
    try { localStorage.setItem('artgame.bx.open', JSON.stringify({ id, view, t: Date.now() })); localStorage.setItem('artgame.place', 'mop') } catch { /* без памяти */ }
    openPlace()
  }
  if (card) return <DealCard id={card} back={() => { setCard(null); load(true) }} open={open} />
  if (err) return <div className="card"><h2>Сделки</h2><p className="muted">{err}</p></div>
  if (!data) return <div className="card muted">Загружаю сделки из Битрикса…</div>
  const s = q.trim().toLowerCase()
  const list = data.deals.filter(d => !s || String(d.id).includes(s) || d.title.toLowerCase().includes(s) || (d.manager || '').toLowerCase().includes(s))
  const groups = {}
  list.forEach(d => { (groups[d.stage] ||= { name: d.stage_name, sort: d.stage_sort + d.category * 1000, items: [], sum: 0 }); groups[d.stage].items.push(d); groups[d.stage].sum += d.sum || 0 })
  const total = list.reduce((a, d) => a + (d.sum || 0), 0)
  return <>
    <MonthStrip onOpen={openMonth} />
    <div className="card"><div className="head"><h2>{data.all ? 'Сделки' : 'Мои сделки'} <span className="muted small">{data.deals.length} · {money(total)}</span></h2>
      <button className="ghost mini" disabled={busy} onClick={() => load(true)}>{busy ? '…' : 'Обновить'}</button></div>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Номер, название или менеджер" />
      {!list.length && <p className="muted">Открытых сделок нет.</p>}
      {Object.entries(groups).sort((a, b) => a[1].sort - b[1].sort).map(([id, g]) => {
        const on = s || openSt[id]
        const stale = g.items.filter(d => ageDays(d.modified) >= IDLE).length
        return <div key={id} className="stage">
          <div className="stagehead" onClick={() => setOpenSt({ ...openSt, [id]: !openSt[id] })}>
            <span>{on ? '▾' : '▸'} {g.name}</span>
            <span className="small"><b>{g.items.length}</b> · {money(g.sum)}{stale ? <span className="badge hot">{stale} стоят</span> : null}</span>
          </div>
          {on && g.items.map(d => { const age = ageDays(d.modified)
            return <div key={d.id} className="qrow" onClick={() => setCard(d.id)}>
              <div className="qmain"><div><b>№ {d.id}</b> {cleanTitle(d.title, d.id)}</div>
                <div className="small muted">{[d.city, d.area ? d.area + ' м²' : '', money(d.sum), d.manager].filter(Boolean).join(' · ')}</div></div>
              <span className={'badge' + (age >= IDLE ? ' hot' : '')}>{age ? `${age} дн.` : 'сегодня'}</span>
            </div> })}
        </div> })}
    </div>
  </>
}

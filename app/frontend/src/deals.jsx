import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { DealCard } from './dealcard.jsx'
import { ageDays, cleanTitle, money } from './crm.jsx'

export const DEAL_ROLES = new Set(['mop', 'mop_vip', 'head'])
const IDLE = 3   // дней без движения — красный бейдж (как mop.today.idle_days)

// Сделки воронкой (HEAD 05.11): воронка → лента стадий с количеством и точкой «стоят» → список одной стадии.
// По умолчанию открыта стадия, где есть застрявшие сделки. Действия — в карточке сделки.
export function Deals({ initial, openPlace }) {
  const [card, setCard] = useState(initial || null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [cat, setCat] = useState(0)        // воронка: 0 Продажи (основная), 13 Дизайн
  const [mgr, setMgr] = useState(0)        // HEAD: фильтр по менеджеру
  const [st, setSt] = useState(null)       // стадия: id | 'all' | null — сама выберет
  const load = fresh => { setBusy(true); setErr(''); return api(`/bx/deals${fresh ? '?fresh=1' : ''}`).then(setData, e => setErr(e.message)).finally(() => setBusy(false)) }
  useEffect(() => { load(false) }, [])
  const open = (id, view, calc) => {
    try {
      if (calc) {   // калькулятор рабочего места читает своё состояние из ag-rm-calc: подставляем площадь и сложность сделки
        const S = JSON.parse(localStorage.getItem('ag-rm-calc') || '{}')
        S.tab = calc.service === 'print' ? 'print' : 'paint'
        if (calc.service === 'print') S.print = { ...(S.print || { design: 'S' }), m2: calc.area || S.print?.m2 || 25 }
        else S.paint = { ...(S.paint || { own: 30000, design: 'M' }), m2: calc.area || S.paint?.m2 || 60, level: calc.level || S.paint?.level || 'Средний' }
        localStorage.setItem('ag-rm-calc', JSON.stringify(S))
      }
      localStorage.setItem('artgame.bx.open', JSON.stringify({ id, view, t: Date.now() })); localStorage.setItem('artgame.place', 'mop')
    } catch { /* без памяти */ }
    openPlace()
  }
  if (card) return <DealCard id={card} back={() => { setCard(null); load(true) }} open={open} />
  if (err) return <div className="card"><h2>Сделки</h2><p className="muted">{err}</p></div>
  if (!data) return <div className="card muted">Загружаю сделки из Битрикса…</div>
  const s = q.trim().toLowerCase()
  const mine = data.deals.filter(d => !mgr || d.manager_id === mgr)
  const list = mine.filter(d => d.category === cat && (!s || String(d.id).includes(s) || d.title.toLowerCase().includes(s) || (d.manager || '').toLowerCase().includes(s)))
  const groups = {}
  list.forEach(d => { (groups[d.stage] ||= { name: d.stage_name, sort: d.stage_sort, items: [], sum: 0, stale: 0 }); const g = groups[d.stage]; g.items.push(d); g.sum += d.sum || 0; if (ageDays(d.active || d.modified) >= IDLE) g.stale++ })
  const stages = Object.entries(groups).sort((a, b) => a[1].sort - b[1].sort)
  const total = list.reduce((a, d) => a + (d.sum || 0), 0)
  const funnels = Object.entries(data.funnels || { 0: 'Продажи', 13: 'Дизайн' }).map(([k, name]) => [+k, name, mine.filter(d => d.category === +k).length])
  const cur = s ? 'all' : st && (st === 'all' || groups[st]) ? st : (stages.find(([, g]) => g.stale) || stages[0] || ['all'])[0]
  const shown = cur === 'all' ? stages : stages.filter(([id]) => id === cur)
  const row = d => { const age = ageDays(d.active || d.modified)
    return <div key={d.id} className="qrow deal" onClick={() => setCard(d.id)}>
      <span className="ic deal">№</span>
      <div className="qmain"><div className="qt"><b>№ {d.id}</b> {cleanTitle(d.title, d.id)}</div>
        <div className="small muted">{[d.city, d.area ? d.area + ' м²' : '', money(d.sum), data.all ? d.manager : ''].filter(Boolean).join(' · ')}</div></div>
      <span className={'badge' + (age >= IDLE ? ' hot' : '')}>{age ? `${age} дн.` : 'сегодня'}</span>
    </div> }
  return <>
    <div className="card"><div className="head"><h2>{data.all ? 'Сделки' : 'Мои сделки'} <span className="muted small">{list.length} · {money(total)}</span></h2>
      <button className="ghost mini" disabled={busy} onClick={() => load(true)}>{busy ? '…' : 'Обновить'}</button></div>
      <div className="segf">{funnels.map(([k, name, n]) => <button key={k} className={cat === k ? 'on' : ''} onClick={() => { setCat(k); setSt(null) }}>{name} <span>{n}</span></button>)}</div>
      {data.all && data.managers.length > 1 && <div className="chips sub"><button className={!mgr ? 'on' : ''} onClick={() => setMgr(0)}>Все</button>
        {data.managers.map(([id, name]) => <button key={id} className={mgr === id ? 'on' : ''} onClick={() => setMgr(id)}>{name.split(' ')[0]}</button>)}</div>}
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Номер, название или менеджер" />
    </div>
    {stages.length > 0 && <div className="chips scroll">
      <button className={cur === 'all' ? 'on' : ''} onClick={() => setSt('all')}>Все <span>{list.length}</span></button>
      {stages.map(([id, g]) => <button key={id} className={cur === id ? 'on' : ''} onClick={() => setSt(id)}>{g.name} <span>{g.items.length}</span>{g.stale ? <i className="dot" /> : null}</button>)}
    </div>}
    <div className="card">
      {!list.length && <p className="muted">В этой воронке открытых сделок нет.</p>}
      {shown.map(([id, g]) => <div key={id} className="stage">
        <div className="stagehead">
          <span>{g.name}</span>
          <span className="small"><b>{g.items.length}</b> · {money(g.sum)}{g.stale ? <span className="badge hot">{g.stale} стоят</span> : null}</span>
        </div>
        {g.items.map(row)}
      </div>)}
    </div>
  </>
}

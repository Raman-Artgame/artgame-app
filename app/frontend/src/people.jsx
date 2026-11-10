import React, { useEffect, useState } from 'react'
import { api } from './api.js'

// Только HEAD: назначить роль и зоны, закрыть вход ушедшему (история остаётся).
export function People({ ROLE, ZONE }) {
  const [list, setList] = useState(null)
  const load = () => api('/people').then(setList, () => setList([]))
  useEffect(() => { load() }, [])
  if (!list) return <div className="card muted">Загрузка…</div>
  const save = (id, body) => api(`/people/${id}`, { method: 'POST', body }).then(load)
  const pendingFirst = [...list].sort((a, b) => (a.status === 'pending' ? -1 : 0) - (b.status === 'pending' ? -1 : 0))
  return <div className="card"><h2>Команда</h2>
    {pendingFirst.map(p => <div key={p.id} className="person">
      <div><b>{p.full_name}</b> {p.tg_username && <span className="muted small">@{p.tg_username}</span>}
        {p.status === 'pending' && <span className="tag st-rejected">ждёт роли</span>}
        {p.status === 'blocked' && <span className="tag">вход закрыт</span>}</div>
      <select disabled={p.role_code === 'head'} value={p.role_code || ''} onChange={e => save(p.id, { role_code: e.target.value })}>
        <option value="" disabled>— роль —</option>
        {Object.entries(ROLE).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
      </select>
      <div className="zones">{Object.entries(ZONE).map(([z, t]) => {
        const on = p.zones.includes(z)
        return <button key={z} className={on ? '' : 'ghost'} onClick={() => save(p.id, { zones: on ? p.zones.filter(x => x !== z) : [...p.zones, z] })}>{t}</button>
      })}</div>
      {p.role_code !== 'head' && (p.status === 'blocked'
        ? <a onClick={() => save(p.id, { status: 'active' })}>открыть вход</a>
        : p.status === 'active' && <a onClick={() => confirm(`Закрыть вход: ${p.full_name}?`) && save(p.id, { status: 'blocked' })}>закрыть вход</a>)}
    </div>)}
  </div>
}

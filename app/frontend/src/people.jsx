import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { startViewAs } from './head.jsx'

const ROLE_ZONE = { support: 'mural', artist: 'mural', artist_pro: 'mural', lead_artist: 'mural', print_operator: 'print', print_master: 'print',
  mop: 'sales', mop_vip: 'sales', lead_designer: 'design', designer_asst: 'design' }
const DZ_ROLES = new Set(['lead_designer', 'designer_asst'])
// Связь с пользователем Битрикса: МОП — свои сделки, дизайнеры — свои задачи воронки «Дизайн РК» (без неё «Дизайн» не открывается).
const BX_ROLES = new Set(['mop', 'mop_vip', ...DZ_ROLES])

// Только HEAD: назначить роль и зоны, закрыть вход ушедшему (история остаётся).
export function People({ ROLE, ZONE }) {
  const [list, setList] = useState(null)
  const [bx, setBx] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api('/people').then(setList, () => setList([]))
  useEffect(() => { load(); api('/bx/users').then(setBx, () => setBx([])) }, [])
  if (!list) return <div className="card muted">Загрузка…</div>
  const save = (id, body) => api(`/people/${id}`, { method: 'POST', body }).then(load, e => setErr(e.message))
  // Роль без зоны не пускает в «Смену»: при первой роли сразу ставим её зону, HEAD может поменять кнопками ниже.
  const setRole = (p, role) => save(p.id, { role_code: role, ...(p.zones.length || !ROLE_ZONE[role] ? {} : { zones: [ROLE_ZONE[role]] }) })
  const pendingFirst = [...list].sort((a, b) => (a.status === 'pending' ? -1 : 0) - (b.status === 'pending' ? -1 : 0))
  return <div className="card"><h2>Команда</h2>{err && <p className="muted">{err}</p>}
    {pendingFirst.map(p => <div key={p.id} className="person">
      <div><b>{p.full_name}</b> {p.tg_username && <span className="muted small">@{p.tg_username}</span>}
        {p.status === 'pending' && <span className="tag st-rejected">ждёт роли</span>}
        {p.status === 'blocked' && <span className="tag">вход закрыт</span>}</div>
      <select disabled={p.role_code === 'head'} value={p.role_code || ''} onChange={e => setRole(p, e.target.value)}>
        <option value="" disabled>— роль —</option>
        {Object.entries(ROLE).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
      </select>
      <div className="zones">{Object.entries(ZONE).map(([z, t]) => {
        const on = p.zones.includes(z)
        return <button key={z} className={on ? '' : 'ghost'} onClick={() => save(p.id, { zones: on ? p.zones.filter(x => x !== z) : [...p.zones, z] })}>{t}</button>
      })}</div>
      {BX_ROLES.has(p.role_code) && <label className="small muted">В Битриксе ({DZ_ROLES.has(p.role_code) ? 'по нему видит свои задачи в «Дизайне» и единицы' : 'его сделки увидит в «Сделках»'})
        <select value={p.bitrix_user_id || 0} onChange={e => save(p.id, { bitrix_user_id: +e.target.value })}>
          <option value={0}>— не связан —</option>
          {(bx || []).map(u => <option key={u.id} value={u.id}>{u.name}{u.position ? ` · ${u.position}` : ''}</option>)}
        </select></label>}
      {p.role_code !== 'head' && p.status !== 'blocked' && <a className="seeas" onClick={() => startViewAs(p.id)}>смотреть как {p.full_name.split(' ')[0]}</a>}
      {p.role_code !== 'head' && (p.status === 'blocked'
        ? <a onClick={() => save(p.id, { status: 'active' })}>открыть вход</a>
        : p.status === 'active' && <a onClick={() => confirm(`Закрыть вход: ${p.full_name}?`) && save(p.id, { status: 'blocked' })}>закрыть вход</a>)}
    </div>)}
  </div>
}

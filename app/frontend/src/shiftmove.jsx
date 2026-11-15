import React, { useState } from 'react'
import { api } from './api.js'

// Смена не на том объекте (HEAD 14.11, 1611 УйДомДонер; 15.11 — и прямо в «Проверке»): HEAD переносит смену и её фото на нужный объект — в базе и на Диске
export function MoveShift({ s, from, onMoved }) {
  const [list, setList] = useState(null)
  const [to, setTo] = useState('')
  const [msg, setMsg] = useState('')
  if (!list) return <a className="small movelink" onClick={() => api('/head/move-targets').then(r => setList(r.filter(o => o.id !== from)), e => setMsg(e.message))}>
    Перенести на другой объект{msg ? ' · ' + msg : ''}</a>
  const go = () => api(`/shifts/${s.id}/move`, { method: 'POST', body: { object_id: +to } })
    .then(r => { setMsg(`Перенесено: ${r.object_id ? `№${r.object_id} ` : ''}${r.object_title}${r.files ? `, фото: ${r.files}` : ''}.`); setTimeout(onMoved, 1200) }, e => setMsg(e.message))
  return <div className="moveshift">
    <select value={to} onChange={e => setTo(e.target.value)}><option value="">— куда перенести —</option>
      {list.map(o => <option key={o.id} value={o.id}>{o.id ? `№${o.id} · ` : ''}{o.title}{o.city ? ` — ${o.city}` : ''}</option>)}</select>
    <div className="seg"><button className="ghost mini" onClick={() => setList(null)}>Отмена</button>
      <button className="mini" disabled={!to} onClick={go}>Перенести смену и фото</button></div>
    {msg && <p className="small muted">{msg}</p>}
  </div>
}


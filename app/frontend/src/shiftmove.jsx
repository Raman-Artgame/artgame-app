import React, { useState } from 'react'
import { api } from './api.js'

// Смена не на том объекте (HEAD 14.11, 1611 УйДомДонер; 15.11 — и прямо в «Проверке»): HEAD переносит смену и её фото на нужный объект — в базе и на Диске.
// HEAD 15.11: «сделай удобный поиск и оставь только актуальные проекты» — сервер отдаёт «Без объекта» и стадии «Выполнение» и оплат, здесь поиск.
export function MoveShift({ s, from, onMoved }) {
  const [list, setList] = useState(null)
  const [to, setTo] = useState(null)
  const [msg, setMsg] = useState('')
  if (!list) return <a className="small movelink" onClick={() => api('/head/move-targets').then(r => setList(r.filter(o => o.id !== from)), e => setMsg(e.message))}>
    Перенести на другой объект{msg ? ' · ' + msg : ''}</a>
  const go = () => api(`/shifts/${s.id}/move`, { method: 'POST', body: { object_id: to.id } })
    .then(r => { setMsg(`Перенесено: ${r.object_id ? `№${r.object_id} ` : ''}${r.object_title}${r.files ? `, фото: ${r.files}` : ''}.`); setTimeout(onMoved, 1200) }, e => setMsg(e.message))
  return <div className="moveshift">
    <ObjSearch list={list} value={to} onPick={setTo} />
    <div className="seg"><button className="ghost mini" onClick={() => { setList(null); setTo(null) }}>Отмена</button>
      <button className="mini" disabled={!to} onClick={go}>Перенести смену и фото</button></div>
    {msg && <p className="small muted">{msg}</p>}
  </div>
}

const objName = o => `${o.id ? `№${o.id} · ` : ''}${o.title}${o.city ? ` — ${o.city}` : ''}`
// Выбор проекта поиском по номеру или названию (HEAD 15.11: «удобный поиск… только актуальные проекты»)
export function ObjSearch({ list, value, onPick }) {
  const [q, setQ] = useState('')
  if (value) return <div className="movepick"><b>{objName(value)}</b><a className="small" onClick={() => onPick(null)}>другой</a></div>
  const words = q.trim().toLowerCase().split(/\s+/).filter(Boolean)
  const found = list.filter(o => words.every(w => objName(o).toLowerCase().includes(w)))
  return <div className="objsearch">
    <input value={q} onChange={e => setQ(e.target.value)} placeholder="🔍 Номер или название" />
    <div className="movelist">{found.map(o => <button key={o.id} className="ghost" onClick={() => onPick(o)}>{objName(o)}</button>)}
      {!found.length && <p className="small muted">Ничего не нашлось</p>}</div></div>
}

// «Расход на проект» на Пульте HEAD (HEAD 15.11: «расходы вывести отдельным удобным блоком»): проект поиском → обычная форма расхода
export function ProjectSpend({ done, cancel, ExpenseForm }) {
  const [list, setList] = useState(null)
  const [obj, setObj] = useState(null)
  const [err, setErr] = useState('')
  React.useEffect(() => { api('/head/move-targets').then(r => setList(r.filter(o => o.id)), e => setErr(e.message)) }, [])
  if (err) return <p className="small muted">{err}</p>
  if (!list) return <p className="small muted">Загрузка…</p>
  return <div className="moveshift">
    <ObjSearch list={list} value={obj} onPick={setObj} />
    {obj ? <ExpenseForm key={obj.id} obj={obj.id} head cancel={cancel} done={done} />
      : <div className="seg"><button className="ghost mini" onClick={cancel}>Отмена</button></div>}
  </div>
}

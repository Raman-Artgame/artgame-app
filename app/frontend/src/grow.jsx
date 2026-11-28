// «Мой путь» на сервере (HEAD 11.11): отметки чек-листа хранятся на сервере, наставник подтверждает или возвращает пункт,
// HEAD и наставники видят прогресс каждого. API — /api/grow (backend/artgame/grow.py).
import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { GROW } from './duties.js'

// Сотрудник: отметки пути code. Отметки, поставленные до 11.11 в телефоне, переносятся на сервер один раз.
const cache = {}
export function useMarks(code, me) {
  const [marks, setMarks] = useState(code ? cache[code] || null : null)
  useEffect(() => { if (!code) return
    api(`/grow/my?path=${code}`).then(d => {
      const local = (() => { try { return JSON.parse(localStorage.getItem(`artgame.grow.${me?.id || 0}.${GROW[code]?.step}`) || '[]') } catch { return [] } })()
      if (!d.marks.length && local.length && !me?._view_as) return api('/grow/my/import', { method: 'POST', body: { path: code, idx: local } })
      return d }).then(d => { cache[code] = d.marks; setMarks(d.marks) }, () => setMarks([]))
  }, [code])
  const flip = async i => {
    const m = (marks || []).find(x => x.idx === i)
    if (m?.confirmed_at) return
    try { const d = await api('/grow/my', { method: 'POST', body: { path: code, idx: i, on: !m?.marked_at } }); cache[code] = d.marks; setMarks(d.marks) }
    catch { /* просмотр или нет связи */ }
  }
  return [marks || [], flip]
}

export const markOf = (marks, i) => marks.find(x => x.idx === i) || {}
const first = n => (n || '').split(' ').slice(0, 2).join(' ')
// Подпись пункта: подтверждён наставником / ждёт / возвращён / нет
export function markLabel(m) {
  if (m.confirmed_at) return [`✓ ${first(m.confirmed_name)}`, 'conf']
  if (m.marked_at) return ['ждёт наставника', 'wait']
  if (m.returned_at) return ['вернули', 'back']
  return ['нет', '']
}
export const countOf = marks => ({ marked: marks.filter(m => m.marked_at).length, conf: marks.filter(m => m.confirmed_at).length })

// Наставник и HEAD: «Путь команды» — у кого сколько, что ждёт подтверждения.
const WHO = 'Подтверждают: саппортов и художников — Главный и Про, Главных — Про, операторов — Мастер печати, дизайнеров — Главный дизайнер, остальных — HEAD.'
export function TeamPath({ head }) {
  const [list, setList] = useState(null)
  const [open, setOpen] = useState(null)
  const [v, setV] = useState({})
  useEffect(() => { api('/grow/team').then(d => setList(d.people), () => setList([])); api('/work/dict').then(d => setV(d.grow || {}), () => {}) }, [])
  if (!list || (!list.length && !head)) return null
  const wait = list.reduce((s, x) => s + x.marks.filter(m => m.marked_at && !m.confirmed_at).length, 0)
  const exam = (x, i) => x.path === 'print_operator' && i === 0   // экзамен оператора = дата ставки после экзамена (HEAD 13.11)
  const act = async (x, idx, ok) => {
    let exam_on = null
    if (ok && exam(x, idx)) {
      const t = window.prompt('С какого дня ставка после экзамена? Например: 01.11', new Date().toLocaleDateString('ru-RU').slice(0, 5))
      if (t === null) return
      const m = t.trim().match(/^(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?$/)
      if (!m) { window.alert('Дата вида 01.11'); return }
      const y = m[3] ? (m[3].length === 2 ? '20' + m[3] : m[3]) : String(new Date().getFullYear())
      exam_on = `${y}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`
    }
    const note = ok ? null : window.prompt('Что доделать? Сотрудник увидит это у себя.')
    if (!ok && note === null) return
    const d = await api('/grow/confirm', { method: 'POST', body: { person_id: x.id, path: x.path, idx, ok, note, exam_on } })
    setList(list.map(y => y.id === x.id ? { ...y, marks: d.marks, print_exam_on: exam(x, idx) ? (ok ? exam_on : null) : y.print_exam_on } : y))
  }
  return <div className="card teampath">
    <span className="tag">Мой путь</span><h2>Путь команды</h2>
    <p className="small muted">{wait ? `Ждут подтверждения: ${wait}` : 'Всё отмеченное подтверждено'}</p>
    {list.map(x => { const g = GROW[x.path]; if (!g) return null
      const c = countOf(x.marks), n = g.check.length, on = open === x.id
      return <div key={x.id} className="tprow">
        <div className="tphead" onClick={() => setOpen(on ? null : x.id)}>
          <div><b>{x.full_name}</b><p className="small muted">{g.step}{x.acting_role ? ' · и.о.' : ''}</p></div>
          <div className="tpnum"><b>{c.conf}/{n}</b>{c.marked - c.conf > 0 && <span className="small">ждёт {c.marked - c.conf}</span>}</div></div>
        <div className="tpbar"><i style={{ width: `${100 * c.conf / n}%` }} /><i className="w" style={{ width: `${100 * (c.marked - c.conf) / n}%` }} /></div>
        {on && g.check.map((it, i) => { const m = markOf(x.marks, i), [lab, cls] = markLabel(m), t = Array.isArray(it) ? it[0] : it
          return <div key={i} className={'tpitem ' + cls}><span>{i + 1}</span><div>{t.replace(/\{([a-z0-9_.]+)\}/g, (_, k) => v[k] != null && v[k] !== '' ? String(v[k]).replace('.', ',') : '…')}
            {Array.isArray(it) && it[1] && <p className="small muted">Как подтверждаем: {it[1]}</p>}
            {m.returned_at && m.note && <p className="small">Вернули: {m.note}</p>}
            {exam(x, i) && x.print_exam_on && <p className="small">Сдан: с {new Date(x.print_exam_on).toLocaleDateString('ru-RU')} принтерные смены по ставке после экзамена</p>}
            {m.marked_at && !m.confirmed_at && <div className="row"><button className="mini" onClick={() => act(x, i, true)}>{exam(x, i) ? 'Сдал — указать дату' : 'Подтвердить'}</button><button className="ghost mini" onClick={() => act(x, i, false)}>Вернуть</button></div>}
            {!m.marked_at && !m.confirmed_at && <button className="ghost mini" onClick={() => act(x, i, true)}>{exam(x, i) ? 'Сдал — указать дату' : 'Подтвердить'}</button>}
            {m.confirmed_at && <button className="ghost mini" onClick={() => act(x, i, false)}>Снять</button>}
          </div><em className="small">{lab}</em></div> })}
      </div> })}
    {!list.length && <p className="small muted">Пока никого на путях.</p>}
    <p className="small muted">{WHO}</p>
  </div>
}

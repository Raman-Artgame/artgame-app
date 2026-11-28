// Знакомство нового сотрудника (HEAD 26.11): после «Принять» — сначала правила роли, ТБ и соглашение о неразглашении и ИС,
// потом приложение. Каждый шаг — «Прочитал» с отпечатком текста; соглашение — ФИО и «Принимаю». Пока не закончил — смены закрыты.
import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import './onboard.css'

async function sha(text) {
  try {
    const b = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
    return [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('')
  } catch {   // не https / старый клиент: простой отпечаток, сервер сохранит как есть
    let h = 0
    for (const c of text) h = (h * 31 + c.charCodeAt(0)) | 0
    return 'js' + (h >>> 0).toString(16).padStart(8, '0')
  }
}

const NAMES = { duties: 'Твоя роль', safety: 'ТБ', nda: 'Соглашение' }

export function Onboard({ me, renderDoc, docText, onDone }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [name, setName] = useState([me.last_name, me.first_name, me.middle_name].filter(Boolean).join(' ') || me.full_name || '')
  const [agree, setAgree] = useState(false)
  const load = () => api('/onboard').then(setD, e => setErr(e.message))
  useEffect(() => { load() }, [])
  useEffect(() => { window.scrollTo?.(0, 0) }, [d?.pending?.[0]])
  if (err && !d) return <div className="wrap"><div className="card"><p className="muted">{err}</p></div></div>
  if (!d) return <div className="wrap muted">Загрузка…</div>
  const cur = d.steps.find(s => !s.done)
  const first = me.first_name || (me.full_name || '').split(' ')[0] || ''   // full_name = «Имя Фамилия» (анкета «Мои данные»)
  const send = async body => {
    setBusy(true); setErr('')
    try { setD({ ...d, ...(await api('/onboard/ack', { method: 'POST', body })) }) } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  const read = async () => send({ doc: cur.doc, version: 'app', sha256: await sha(docText(cur.doc)) })
  const accept = () => send({ doc: 'nda', version: d.nda.version, sha256: d.nda.sha256, full_name: name, agree })
  const bar = <div className="obbar">{d.steps.map(s => <i key={s.doc} className={s.done ? 'ok' : s === cur ? 'on' : ''}><b>{NAMES[s.doc]}</b></i>)}</div>

  if (!cur) return <div className="wrap ob"><div className="card obdone">
    <div className="obok">✓</div><h2>Готово, {first}</h2>
    <p className="muted">Правила прочитаны, соглашение принято. Смены и расходы открыты.</p>
    <p className="small muted">Всё это всегда есть в «Кабинете» → «Правила игры».</p>
    <button onClick={onDone}>В приложение</button></div></div>

  const n = d.steps.indexOf(cur) + 1
  return <div className="ob">
    <div className="wrap obtop"><span className="tag">Знакомство · шаг {n} из {d.steps.length}</span>
      <h1>{n === 1 ? `Добро пожаловать в команду${first ? ', ' + first : ''}` : NAMES[cur.doc]}</h1>
      <p className="muted">{n === 1 ? 'Перед первой сменой — прочитай, как у нас устроено. Займёт минут 10. Пока не закончишь, смены закрыты.' :
        cur.doc === 'safety' ? 'Главное по безопасности на объекте. Это не формальность: от этого зависит жизнь.' :
          'Последний шаг. Прочитай и прими соглашение.'}</p>
      {bar}</div>
    {cur.doc === 'nda' ? <div className="wrap"><div className="card obnda">
      <span className="tag draft">Черновик · проверяет юрист</span>
      <h2>{d.nda.title}</h2><p className="small muted">Версия {d.nda.version}</p>
      {d.nda.sections.map(([t, ps]) => <section key={t}><h3>{t}</h3>{ps.map((x, i) => <p key={i}>{x}</p>)}</section>)}
    </div>
    <div className="card obsign">
      <label>ФИО полностью<input value={name} onChange={e => setName(e.target.value)} placeholder="Фамилия Имя Отчество" /></label>
      <label className="obcheck"><input type="checkbox" checked={agree} onChange={e => setAgree(e.target.checked)} />
        <span>Прочитал(а) полностью и согласен(на) с условиями</span></label>
      <p className="small muted">Сохраним ФИО, телефон {d.phone || ''}, дату, время и версию текста.</p>
    </div></div> : renderDoc(cur.doc)}
    <div className="obfoot"><div className="wrap">
      {err && <p className="obfail">{err}</p>}
      {cur.doc === 'nda' ? <button disabled={busy || !agree || name.trim().split(/\s+/).length < 2} onClick={accept}>{busy ? 'Сохраняю…' : 'Принимаю'}</button> :
        <button disabled={busy} onClick={read}>{busy ? 'Сохраняю…' : 'Прочитал(а), дальше'}</button>}
    </div></div>
  </div>
}

// Для HEAD в карточке кандидата: прошёл ли знакомство и когда принял соглашение.
export function OnboardStatus({ ob }) {
  if (!ob) return null
  const t = x => x ? new Date(x).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : ''
  return <div className="obstat"><b>{ob.done ? 'Знакомство пройдено' : 'Знакомство: ещё не закончил — смены закрыты'}</b>
    {ob.steps.map(s => <div key={s.doc} className={s.done ? 'ok' : ''}><span>{s.done ? '✓' : '○'} {s.title}</span>
      <em>{s.done ? t(s.at) + (s.doc === 'nda' ? ` · версия ${s.version}` : '') : 'не прочитано'}</em></div>)}</div>
}

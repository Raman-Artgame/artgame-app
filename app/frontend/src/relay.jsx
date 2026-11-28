import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Sheet } from './ui.jsx'

// Эстафета сделки (HEAD 26.11 «отлично, давай так сделаем»): МОП → дизайн → производство → сдача → закрытие.
// Полоска пути — пять отрезков, у каждого свой хозяин; «В производство» — одна кнопка МОП вместо «Перевести в работу»
// и «Передать куратору ГИП»: стадия, старт, сдача и ГИП за один раз.

export function DealPath({ dealId, stage, reload = 0 }) {
  const [d, setD] = useState(null)
  useEffect(() => { api(`/deals/${dealId}/path${stage ? `?stage=${encodeURIComponent(stage)}` : ''}`).then(setD, () => setD(null)) }, [dealId, stage, reload])
  if (!d) return null
  const now = d.steps.find(s => s.state === 'now')
  return <div className="dpath" aria-label="Путь сделки">
    <div className="dpbar">{d.steps.map(s => <span key={s.key} className={'dp ' + s.state} title={s.title + (s.detail ? ': ' + s.detail : '')} />)}</div>
    <div className="dplbl">{d.steps.map(s => <span key={s.key} className={s.state}>{s.title}</span>)}</div>
    {now?.detail && <div className="small muted dpnow">Дальше: {now.detail}</div>}
  </div>
}

const iso = d => d.toISOString().slice(0, 10)
const plus = (s, n) => { const d = new Date(s); d.setDate(d.getDate() + n); return iso(d) }
const dm = s => s ? s.slice(8, 10) + '.' + s.slice(5, 7) : ''

export function ProductionSheet({ dealId, onClose, onDone, onFill }) {
  const [f, setF] = useState(null)
  const [gip, setGip] = useState(0)
  const [gip2, setGip2] = useState(0)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => {
    api(`/bx/deals/${dealId}/production`).then(r => {
      setF(r); setGip(r.gip_id || 0); setGip2(r.gip2_id || 0)
      const s = r.start || plus(iso(new Date()), 1)
      setStart(s); setEnd(r.end || plus(s, 7))
    }, e => setErr(e.message))
  }, [dealId])
  const ok = f && gip && start && end && end >= start && !f.missing.length
  const send = () => { setBusy(true); setErr('')
    api(`/bx/deals/${dealId}/production`, { method: 'POST', body: { gip_id: gip, gip2_id: gip2 === gip ? 0 : gip2, start, end } })
      .then(r => onDone(r.bx === 'off' ? 'Передано в производство. В Битрикс не записано: запись выключена.' : 'Передано в производство: ГИП получил сообщение.'),
        e => { setErr(e.message); setBusy(false) }) }
  return <Sheet title="В производство" onClose={onClose}>
    {!f && !err && <p className="muted">Загрузка…</p>}
    {f && <>
      <p className="small muted">{f.in_work ? 'Сделка уже в работе: здесь меняются ГИП и сроки.' : 'Стадия станет «Выполнение проекта», ГИП получит сообщение, заметка в Битрикс запишется сама.'}</p>
      <div className="prodsk">{f.sketch ? <>
        {f.sketch.thumb && <img src={f.sketch.thumb} alt={f.sketch.name} />}
        <div><span className="okmark small">✓ эскиз в работу</span><div className="small">{f.sketch.name}</div></div></>
        : <div className="small why">Утверждённого эскиза нет{f.design_open ? `, задач на дизайн в работе: ${f.design_open}` : ''}. Передать можно, ГИП увидит это в сообщении.</div>}
      </div>
      <label>Куратор ГИП
        <select value={gip} onChange={e => setGip(+e.target.value)}>
          <option value={0}>Выбрать…</option>
          {f.candidates.map(c => <option key={c.id} value={c.id}>{c.full_name} · {c.role_title}{c.acting ? ' (и.о.)' : ''}</option>)}
        </select></label>
      {!!gip && <label>Второй куратор ГИП <span className="muted">(если нужен)</span>
        <select className="gip2" value={gip2 === gip ? 0 : gip2} onChange={e => setGip2(+e.target.value)}>
          <option value={0}>Нет</option>
          {f.candidates.filter(c => c.id !== gip).map(c => <option key={c.id} value={c.id}>{c.full_name} · {c.role_title}{c.acting ? ' (и.о.)' : ''}</option>)}
        </select></label>}
      <div className="two">
        <label>Старт<input type="date" value={start} onChange={e => { setStart(e.target.value); if (end < e.target.value) setEnd(e.target.value) }} /></label>
        <label>Сдача<input type="date" value={end} min={start} onChange={e => setEnd(e.target.value)} /></label>
      </div>
      <p className="small muted">Людей на объект ставят кураторы ГИП (или HEAD). Дату старта клиенту — после подтверждения загрузки.</p>
      {!!f.missing.length && <div className="lockbox"><b>🔒 Пока не заполнено:</b>
        <div>{f.missing.map(m => <span key={m} className="miss">{m}</span>)}</div>
        {onFill && <button className="mini" onClick={onFill}>Заполнить карточку</button>}</div>}
    </>}
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
    <button disabled={!ok || busy} onClick={send}>{busy ? 'Передаю…' : f?.in_work ? 'Сохранить' : `Передать${start ? ' · старт ' + dm(start) : ''}`}</button>
  </Sheet>
}

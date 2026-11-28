// Пробный день кандидата (HEAD 28.11): куратор ГИП (или кого назначил HEAD) руководит кандидатом на объекте и после смены
// оценивает: звёзды, 7 обязательных пунктов, итог «брать / под вопросом / не брать» и подробный комментарий.
// Карточка — вверху приложения у оценщика, пока не оценено; решение принимает HEAD в «Кандидатах».
import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import './hrtrial.css'

export function TrialInbox({ me, children }) {
  const [items, setItems] = useState([])
  const [open, setOpen] = useState(null)
  const load = () => api('/hr/trials').then(x => setItems(x.items || []), () => setItems([]))
  useEffect(() => { if (!me._view_as) load() }, [])
  // одна и та же структура всегда — приложение под карточкой не пересоздаётся, когда список пришёл
  return <>{!open && items.length > 0 && <div className="wrap trinbox">{items.map(x => <button key={x.id} className="trcard" onClick={() => setOpen(x.id)}>
    <span className="tag">Пробный день · {x.trial_on ? `${x.trial_on.slice(8, 10)}.${x.trial_on.slice(5, 7)}` : 'дата уточняется'}</span>
    <b>{x.full_name}</b><em>{x.dir_title}{x.object ? ` · ${x.object}` : ''}</em>
    <span className="trgo">Ты руководишь им на объекте. После смены — оценить →</span></button>)}</div>}
    {open && <TrialForm id={open} close={() => { setOpen(null); load() }} />}
    <div className="trapp" hidden={!!open}>{children}</div></>
}

function TrialForm({ id, close }) {
  const [c, setC] = useState(null)
  const [v, setV] = useState({ stars: 0, items: {}, verdict: '', comment: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => { api(`/hr/trials/${id}`).then(setC, e => setErr(e.message)); window.scrollTo?.(0, 0) }, [])
  if (!c) return <div className="wrap"><div className="card muted">{err || 'Загрузка…'}</div></div>
  const left = c.items.filter(([k]) => !v.items[k]).length
  const need = Math.max(0, c.comment_min - v.comment.trim().replace(/\s+/g, ' ').length)
  const ready = v.stars && !left && v.verdict && !need
  const send = async () => {
    setBusy(true); setErr('')
    try { await api(`/hr/trials/${id}`, { method: 'POST', body: v }); close() } catch (e) { setErr(e.message) }
    setBusy(false)
  }
  return <div className="wrap trform">
    <button className="ghost mini" onClick={close}>← Назад</button>
    <div className="card"><span className="tag">Пробный день · {c.trial_on ? `${c.trial_on.slice(8, 10)}.${c.trial_on.slice(5, 7)}` : ''}</span>
      <h2>{c.full_name}</h2><p className="small muted">{c.dir_title}{c.object ? ` · объект «${c.object}»` : ''}</p>
      {c.brief.length > 0 && <div className="trbrief">{c.brief.map(([k, x]) => <div key={k}><span>{k}</span><b>{x}</b></div>)}</div>}
      {c.photos.length > 0 && <div className="trpics">{c.photos.map(u => <img key={u} src={u} alt="" loading="lazy" />)}</div>}
      <p className="small muted">Ты руководишь кандидатом в этот день. Оценка уходит HEAD — он решает, брать ли. Кандидат её не видит.</p></div>

    <div className="card"><h3>Общая оценка</h3>
      <div className="trstars">{[1, 2, 3, 4, 5].map(n => <button key={n} type="button" className={n <= v.stars ? 'on' : ''} aria-label={`${n} из 5`} onClick={() => setV({ ...v, stars: n })}>★</button>)}</div></div>

    <div className="card"><h3>Обязательные пункты</h3>
      {c.items.map(([k, t]) => <div key={k} className="tritem"><p>{t}</p>
        <div className="trseg">{Object.entries(c.marks).map(([m, mt]) => <button key={m} type="button" className={(v.items[k] === m ? 'on ' : '') + m}
          onClick={() => setV({ ...v, items: { ...v.items, [k]: m } })}>{mt}</button>)}</div></div>)}</div>

    <div className="card"><h3>Итог: подходит человек?</h3>
      <div className="trseg big">{Object.entries(c.verdicts).map(([m, mt]) => <button key={m} type="button" className={(v.verdict === m ? 'on ' : '') + m}
        onClick={() => setV({ ...v, verdict: m })}>{mt}</button>)}</div>
      <label className="small muted trlbl">Подробный комментарий: что делал, что получилось, что нет, брать ли и почему</label>
      <textarea rows={6} value={v.comment} onChange={e => setV({ ...v, comment: e.target.value })}
        placeholder="Например: пришёл в 9:05, сразу включился в подготовку. Проклейку делал аккуратно, но медленно. Кисть держит уверенно, фон ровный. Указания понимает с первого раза…" />
      <p className={'small ' + (need ? 'muted' : 'trok')}>{need ? `Ещё ${need} знаков` : '✓ Достаточно подробно'}</p></div>

    <div className="trfoot"><div className="wrap">
      {err && <p className="hrerr">{err}</p>}
      {!ready && <p className="small muted trleft">{[!v.stars && 'звёзды', left && `пункты (${left})`, !v.verdict && 'итог', need && 'комментарий'].filter(Boolean).join(' · ')}</p>}
      <button disabled={!ready || busy} onClick={send}>{busy ? 'Отправляю…' : 'Отправить оценку HEAD'}</button></div></div>
  </div>
}

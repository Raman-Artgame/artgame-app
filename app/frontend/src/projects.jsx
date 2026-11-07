import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Skeleton, cleanTitle, money } from './crm.jsx'

// «Проекты» — общая вкладка (HEAD 06.11): кто где находится и сколько дней осталось до сдачи. Данные — сделки в работе
// из Битрикса (срок из расчёта или договора) и смены из приложения (сделано, кто был на объекте последние дни).
const STATE = { late: ['Просрочен', 'hot'], today: ['Сдача сегодня', 'warn'], quiet: ['Тихо 3+ дня', 'warn'], idle: ['Смен ещё нет', ''], ok: ['Идёт', 'ok'], soon: ['Старт скоро', ''], closing: ['Сдан · ждём оплату и акты', ''] }
const dmy = s => s ? s.split('-').reverse().slice(0, 2).join('.') : ''
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return h >= 11 && h <= 14 ? c : m === 1 ? a : m >= 2 && m <= 4 ? b : c }
export const leftText = x => x.left == null ? (x.working ? 'срок не задан' : 'ждёт старта') : x.left < 0 ? `просрочен на ${-x.left} ${plural(-x.left, 'день', 'дня', 'дней')}`
  : x.left === 0 ? 'сдача сегодня' : `осталось ${x.left} ${plural(x.left, 'день', 'дня', 'дней')}`

export function Projects({ openDeal }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [seg, setSeg] = useState('work')
  const load = fresh => { setBusy(true); setErr(''); return api(`/bx/projects${fresh ? '?fresh=1' : ''}`).then(setD, e => setErr(e.message)).finally(() => setBusy(false)) }
  useEffect(() => { load(false) }, [])
  if (err && !d) return <div className="card"><h2>Проекты</h2><p className="muted">{err}</p></div>
  if (!d) return <Skeleton n={4} />
  const list = d.projects.filter(x => seg === 'all' || (seg === 'work' ? x.working : seg === 'closing' ? x.closing : x.state === 'soon'))
  const row = x => {
    const [st, cls] = STATE[x.state]
    const pct = x.progress != null ? x.progress : x.working && x.norm.term && x.left != null ? Math.min(100, Math.max(0, Math.round((1 - x.left / x.norm.term) * 100))) : 0
    return <div key={x.id} className="proj" onClick={() => openDeal && openDeal(x.id)}>
      <div className="top">
        <div><b>№ {x.id}</b> {cleanTitle(x.title, x.id)}
          <div className="meta">{[x.city, x.area ? `${x.area} м²` : '', x.level, x.manager ? `МОП ${x.manager.split(' ')[0]}` : ''].filter(Boolean).join(' · ')}</div></div>
        <span className={'left ' + (x.state === 'late' ? 'late' : x.left != null && x.left <= 2 ? 'soon' : '')}>{x.left == null ? '—' : x.left < 0 ? `−${-x.left} дн.` : `${x.left} дн.`}</span>
      </div>
      {x.working && <div className={'prog ' + (x.state === 'late' ? 'late' : x.progress >= 100 ? 'ok' : '')}><i style={{ width: pct + '%' }} /></div>}
      <div className="meta">
        {x.working ? <>{x.start ? `старт ${dmy(x.start)}` : 'старт не отмечен'}{x.due ? ` · сдача ${dmy(x.due)}` : ''} · {leftText(x)}
          {x.norm.shifts ? ` · смен ${x.done.shifts} из ${x.norm.shifts}` : x.done.shifts ? ` · смен ${x.done.shifts}` : ''}</>
          : <>{x.closing && x.start ? `старт ${dmy(x.start)} · ` : ''}{x.stage_name}{x.norm.term ? ` · по норме ${x.norm.term} раб. дн.` : ''}{x.sum ? ` · ${money(x.sum)}` : ''}</>}
      </div>
      <div className="meta" style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 6 }}>
        <span className={'badge ' + cls} style={{ marginLeft: 0 }}>{st}</span>
        {x.people.length ? <span className="who">{x.people.map(n => <span key={n}>{n.split(' ')[0]}</span>)}</span> : x.working ? <span className="small muted">на объекте никого не отмечено</span> : null}
      </div>
    </div>
  }
  return <>
    <div className="card">
      <div className="head"><div><h2>Проекты</h2><div className="small muted">в работе {d.counts.work}{d.counts.late ? <span className="badge hot">{d.counts.late} просрочено</span> : null}</div></div>
        <button className="ghost mini" disabled={busy} onClick={() => load(true)}>{busy ? '…' : 'Обновить'}</button></div>
      <div className="segf">
        <button className={seg === 'work' ? 'on' : ''} onClick={() => setSeg('work')}>В работе <span>{d.counts.work}</span></button>
        <button className={seg === 'soon' ? 'on' : ''} onClick={() => setSeg('soon')}>Старт скоро <span>{d.counts.soon}</span></button>
        <button className={seg === 'closing' ? 'on' : ''} onClick={() => setSeg('closing')}>Закрытие <span>{d.counts.closing || 0}</span></button>
        <button className={seg === 'all' ? 'on' : ''} onClick={() => setSeg('all')}>Все <span>{d.projects.length}</span></button>
      </div>
      {!list.length && <p className="muted">{seg === 'work' ? 'Сейчас объектов в работе нет.' : 'Пусто.'}</p>}
      {list.map(row)}
    </div>
    <p className="small muted" style={{ padding: '0 4px' }}>Старт и сдача — из полей сделки «Старт факт» / «Окончание план», иначе срок из расчёта в карточке сделки или из договора; «сделано смен» и «кто на объекте» — из смен, отмеченных в приложении.</p>
  </>
}

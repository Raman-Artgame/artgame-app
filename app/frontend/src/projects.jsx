import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Skeleton, cleanTitle, money } from './crm.jsx'
import { Gallery } from './objects.jsx'

// «Проекты» — общая вкладка (HEAD 06.11): кто где находится и сколько дней осталось до сдачи. Данные — сделки в работе
// из Битрикса (срок из расчёта или договора) и смены из приложения (сделано, кто был на объекте последние дни).
const STATE = { late: ['Просрочен', 'hot'], today: ['Сдача сегодня', 'warn'], quiet: ['Тихо 3+ дня', 'warn'], idle: ['Смен ещё нет', ''], ok: ['Идёт', 'ok'], soon: ['Старт скоро', ''], closing: ['Сдан · ждём оплату и акты', ''] }
const dmy = s => s ? s.split('-').reverse().slice(0, 2).join('.') : ''
const plural = (n, a, b, c) => { const m = n % 10, h = n % 100; return h >= 11 && h <= 14 ? c : m === 1 ? a : m >= 2 && m <= 4 ? b : c }
export const leftText = x => x.left == null ? (x.working ? 'срок не задан' : 'ждёт старта') : x.left < 0 ? `просрочен на ${-x.left} ${plural(-x.left, 'день', 'дня', 'дней')}`
  : x.left === 0 ? 'сдача сегодня' : `осталось ${x.left} ${plural(x.left, 'день', 'дня', 'дней')}`

const COND = [['at_height', 'Высота'], ['outdoor', 'Улица'], ['hard_surface', 'Сложная поверхность']]
const initials = n => n.split(' ').slice(0, 2).map(w => w[0]).join('')

// «Проекты» (HEAD 08.11): один раздел вместо «Проектов» и «Объектов». Карточки с эскизом, сроком и командой;
// внутри — что за объект, условия, ход работ, эскизы, фото с объекта и продакшн.
export function Projects({ openDeal, me }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [seg, setSeg] = useState('work')
  const [open, setOpen] = useState(null)
  const load = fresh => { setBusy(true); setErr(''); return api(`/bx/projects${fresh ? '?fresh=1' : ''}`).then(setD, e => setErr(e.message)).finally(() => setBusy(false)) }
  useEffect(() => { load(false) }, [])
  if (err && !d) return <div className="card"><h2>Проекты</h2><p className="muted">{err}</p></div>
  if (!d) return <Skeleton n={4} />
  if (open) return <ProjectCard x={open} me={me} back={() => setOpen(null)} openDeal={openDeal} />
  const list = d.projects.filter(x => seg === 'all' || (seg === 'work' ? x.working : seg === 'closing' ? x.closing : x.state === 'soon'))
  return <>
    <div className="card">
      <div className="head"><div><h2>Проекты</h2><div className="small muted">в работе {d.counts.work}{d.counts.late ? <span className="badge hot">{d.counts.late} просрочено</span> : null}</div></div>
        <button className="ghost mini" disabled={busy} onClick={() => load(true)}>{busy ? '…' : 'Обновить'}</button></div>
      <div className="segf">
        <button className={seg === 'work' ? 'on' : ''} onClick={() => setSeg('work')}>В работе <span>{d.counts.work}</span></button>
        <button className={seg === 'soon' ? 'on' : ''} onClick={() => setSeg('soon')}>Скоро <span>{d.counts.soon}</span></button>
        <button className={seg === 'closing' ? 'on' : ''} onClick={() => setSeg('closing')}>Закрытие <span>{d.counts.closing || 0}</span></button>
        <button className={seg === 'all' ? 'on' : ''} onClick={() => setSeg('all')}>Все <span>{d.projects.length}</span></button>
      </div>
      {!list.length && <p className="muted">{seg === 'work' ? 'Сейчас объектов в работе нет.' : 'Пусто.'}</p>}
    </div>
    <div className="pcards">{list.map(x => <PCard key={x.id} x={x} onOpen={() => setOpen(x)} />)}</div>
  </>
}

const pct = x => x.progress != null ? x.progress : x.working && x.norm.term && x.left != null ? Math.min(100, Math.max(0, Math.round((1 - x.left / x.norm.term) * 100))) : 0

function PCard({ x, onOpen }) {
  const [st, cls] = STATE[x.state]
  return <div className="pcard" onClick={onOpen} role="button" tabIndex={0}>
    <div className="cover" style={x.cover ? { backgroundImage: `url(${x.cover})` } : undefined}>
      {!x.cover && <span className="num">№{x.id}</span>}
      <span className={'badge ' + cls}>{st}</span>
      {x.now?.length > 0 && <span className="live">● на объекте {x.now.length}</span>}
      <span className={'left ' + (x.state === 'late' ? 'late' : x.left != null && x.left <= 2 ? 'soon' : '')}>{x.left == null ? '—' : x.left < 0 ? `−${-x.left} дн.` : `${x.left} дн.`}</span>
    </div>
    <div className="pbody">
      <b>{cleanTitle(x.title, x.id)}</b>
      <div className="meta">{[`№ ${x.id}`, x.city, x.area ? `${x.area} м²` : '', x.level].filter(Boolean).join(' · ')}</div>
      {x.working && <div className={'prog ' + (x.state === 'late' ? 'late' : x.progress >= 100 ? 'ok' : '')}><i style={{ width: pct(x) + '%' }} /></div>}
      <div className="pfoot">
        <span className="avas">{x.people.slice(0, 4).map(n => <i key={n} title={n}>{initials(n)}</i>)}{x.people.length > 4 && <i>+{x.people.length - 4}</i>}</span>
        <span className="small muted">{x.files?.design ? `эскизов ${x.files.design}` : 'эскиза нет'}{x.files?.media ? ` · фото ${x.files.media}` : ''}</span>
      </div>
    </div>
  </div>
}

function ProjectCard({ x, me, back, openDeal }) {
  const [st, cls] = STATE[x.state]
  const c = x.cond || {}
  const kv = [['Город', x.city], ['Адрес', x.address], ['Площадь', x.area ? `${x.area} м²` : ''], ['Сложность', x.level || 'МОП ещё не указал'],
    ['Старт', x.start ? dmy(x.start) : ''], ['Сдача', x.due ? dmy(x.due) : ''], ['Смены', x.norm.shifts ? `${x.done.shifts} из ${x.norm.shifts}` : x.done.shifts ? String(x.done.shifts) : ''],
    ['Состав по норме', x.norm.crew ? `${x.norm.crew} чел.` : ''], ['Сделано', x.done.m2 ? `${x.done.m2} м²` : ''], ['МОП', x.manager], ['Сумма', x.sum ? money(x.sum) : '']].filter(([, v]) => v)
  return <>
    <div className="phero" style={x.cover ? { backgroundImage: `linear-gradient(180deg, rgba(11,11,13,.15), rgba(11,11,13,.85)), url(${x.cover})` } : undefined}>
      <button className="ghost mini back" onClick={back}>← Проекты</button>
      <div><span className={'badge ' + cls}>{st}</span><h1>{cleanTitle(x.title, x.id)}</h1>
        <p className="small">№ {x.id} · {leftText(x)}</p></div>
    </div>
    <div className="card">
      {x.working && <div className={'prog ' + (x.state === 'late' ? 'late' : x.progress >= 100 ? 'ok' : '')}><i style={{ width: pct(x) + '%' }} /></div>}
      <div className="conds light">{COND.map(([k, t]) => <span key={k} className={c[k] ? 'on' : ''}>{c[k] ? '● ' : ''}{t}</span>)}</div>
      <div className="kvgrid">{kv.map(([k, v]) => <div key={k}><span>{k}</span><b>{v}</b></div>)}</div>
      {(x.now?.length > 0 || x.people.length > 0) && <><h3>Команда</h3><div className="who">
        {x.now?.map(n => <span key={'n' + n} className="live">● {n}</span>)}
        {x.people.filter(n => !(x.now || []).includes(n)).map(n => <span key={n}>{n}</span>)}</div>
        <p className="small muted">● — смена идёт сейчас; остальные были на объекте последние 4 дня.</p></>}
      {openDeal && <button className="ghost" onClick={() => openDeal(x.id)}>Открыть сделку</button>}
    </div>
    <Gallery obj={{ id: x.id, title: x.title }} me={me} />
  </>
}

import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Skeleton, cleanTitle, money } from './crm.jsx'
import { Gallery } from './objects.jsx'
import { More } from './work.jsx'

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
      <b>{cleanTitle(x.title, x.id)}</b>{x.gip && <span className="small muted"> · ГИП {x.gip.name.split(' ')[0]}</span>}
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
    ['Состав по норме', x.norm.crew ? `${x.norm.crew} чел.` : ''], ['Сделано', x.done.m2 ? `${x.done.m2} м²` : ''], ['МОП', x.manager], ['ГИП', x.gip?.name || ''], ['Сумма', x.sum ? money(x.sum) : '']].filter(([, v]) => v)
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
    {me && ASSIGN.has(me.role_code) && <GipPick x={x} />}
    {me && (SEE_ALL.has(me.role_code) || (x.gip && x.gip.id === me.id)) && <History id={x.id} mine={x.gip?.id === me.id} />}
    <Gallery obj={{ id: x.id, title: x.title }} me={me} />
  </>
}

// ГИП проекта (HEAD 09.11): назначают HEAD и МОП; ГИП — Главный художник, Про или Мастер печати (и «и.о.» этих ролей).
const ASSIGN = new Set(['head', 'mop', 'mop_vip'])
const SEE_ALL = new Set(['head', 'artist_pro'])
function GipPick({ x }) {
  const [list, setList] = useState(null)
  const [cur, setCur] = useState(x.gip?.id || 0)
  const [msg, setMsg] = useState('')
  useEffect(() => { api('/gip/candidates').then(setList, () => setList([])) }, [])
  const save = id => api(`/objects/${x.id}/gip`, { method: 'POST', body: { person_id: id } })
    .then(r => { setCur(r.gip_id || 0); x.gip = r.gip_id ? { id: r.gip_id, name: r.gip_name } : null; setMsg(r.gip_id ? `ГИП — ${r.gip_name}, ему пришло сообщение.` : 'ГИП снят.') }, e => setMsg(e.message))
  return <div className="card gippick"><h3>ГИП проекта</h3>
    <select value={cur} onChange={e => save(+e.target.value)} disabled={!list}>
      <option value={0}>— не назначен —</option>
      {(list || []).map(p => <option key={p.id} value={p.id}>{p.full_name} · {p.acting ? 'и.о. ' : ''}{p.role_title}</option>)}
    </select>
    <p className="small muted">{msg || 'ГИП видит всю историю проекта и принимает его смены.'}</p></div>
}

const ST = { submitted: 'на проверке', approved: 'принято', rejected: 'отклонено', open: 'идёт' }
const dt = s => new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
const tm = s => new Date(s).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
// Вся история проекта для ГИП: кто сколько, по дням — что сделал с фото, расходы с чеками.
function History({ id, mine }) {
  const [h, setH] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api(`/objects/${id}/history`).then(setH, e => setErr(e.message)) }, [id])
  if (err) return <div className="card muted">{err}</div>
  if (!h) return <div className="card muted">Загрузка истории…</div>
  return <div className="card history"><h3>{mine ? 'Ты ГИП · вся история проекта' : 'Вся история проекта'}</h3>
    {h.people.length ? <div className="hpeople">{h.people.map(x => <div key={x.name}><b>{x.name}</b>
      <span className="small muted">{x.shifts} смен · {x.hours} ч{x.m2 ? ` · ${x.m2} м²` : ''}</span></div>)}</div> : <p className="muted">Смен ещё нет.</p>}
    {h.shifts.length > 0 && <><h3>Смены</h3>{h.shifts.map(s => <div key={s.id} className="row">
      <div><b>{s.full_name}</b> · {dt(s.started_at)} {tm(s.started_at)}{s.ended_at ? '–' + tm(s.ended_at) : ''}{s.area_m2 ? ` · ${+s.area_m2} м²` : ''}{s.kind === 'road' ? ' · дорога' : ''}
        {s.backfill && <span className="tag draft">задним числом</span>}
        {s.work_done && <div className="small">Сделал: {s.work_done}</div>}
        {s.reason && <div className="small why">Причина: {s.reason}</div>}
        {(s.photo_before_url || s.photo_after_url) && <div className="pair">{s.photo_before_url && <a href={s.photo_before_full} target="_blank" rel="noreferrer"><img src={s.photo_before_url} alt="до" /></a>}
          {s.photo_after_url && <a href={s.photo_after_full} target="_blank" rel="noreferrer"><img src={s.photo_after_url} alt="после" /></a>}</div>}
        <More x={s} /></div>
      <span className={`tag st-${s.status}`}>{ST[s.status] || s.status}</span></div>)}</>}
    {h.expenses.length > 0 && <><h3>Расходы · {money(h.spent)}</h3>{h.expenses.map(e => <div key={e.id} className="row">
      <div><b>{money(e.amount)}</b> · {e.category} · {e.full_name}<br /><span className="small muted">{dt(e.created_at)}{e.note ? ' · ' + e.note : ''}</span>
        {e.receipt_url && <a href={e.receipt_url} target="_blank" rel="noreferrer"> чек</a>}</div>
      <span className={`tag st-${e.status}`}>{ST[e.status] || e.status}</span></div>)}</>}
  </div>
}

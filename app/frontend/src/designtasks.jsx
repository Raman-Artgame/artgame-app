import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Sheet } from './ui.jsx'
import { cleanTitle } from './crm.jsx'
import { Gallery, Viewer } from './objects.jsx'

// Задачи на дизайн при сделке (HEAD 25.11 «в целом норм, давай попробуем»): МОП жмёт «Нужен дизайн» в карточке сделки —
// сделка остаётся на своей стадии, у дизайнера карточка во вкладке «Дизайн» с его привычными стадиями.
// Единиц задачи не дают: единица одна за весь проект. Переписка с клиентом — в Битриксе, кнопкой из задачи.
const openUrl = u => { const t = window.Telegram?.WebApp; if (t?.openLink && t.initData) t.openLink(u); else window.open(u, '_blank', 'noopener') }
const dm = s => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}` : ''
const today = () => new Date().toISOString().slice(0, 10)
const tone = st => st === 'done' ? ' okt' : st === 'urgent' ? ' hott' : st === 'new' ? ' none' : ''
const who = t => [t.designer || 'дизайнер не назначен', t.deadline ? 'срок ' + dm(t.deadline) : ''].filter(Boolean).join(' · ')

// Эскизы и материалы сделки (HEAD 26.11: «как выгрузить материал?»): дизайнер грузит файл прямо здесь, он сам ложится
// в папку сделки ДИЗАЙН на Диске. Ссылок руками нет. У сделки до стадии работы папки ещё нет — сервер заводит её сам.
export function DealFiles({ dealId, me }) {
  const [ok, setOk] = useState(null)
  useEffect(() => { api(`/design/deal/${dealId}/object`, { method: 'POST' }).then(() => setOk(true), () => setOk(false)) }, [dealId])
  if (ok === null) return <p className="muted small">Загрузка…</p>
  if (!ok) return <p className="small why">Не удалось открыть папку сделки. Обновите страницу; не поможет — напишите HEAD.</p>
  return <Gallery obj={{ id: dealId }} me={me} only={['design']} bare />
}

// То же для МОП, только посмотреть: что дизайнер уже загрузил.
function SeeFiles({ dealId }) {
  const [list, setList] = useState([])
  const [open, setOpen] = useState(null)
  useEffect(() => { api(`/objects/${dealId}/files?kind=design`).then(setList, () => setList([])) }, [dealId])
  if (!list.length) return null
  return <><p className="dtcap dtfiles">Эскизы · {list.length}</p>
    {list.map(f => <div key={f.id} className="dtrow click" onClick={() => setOpen(f)}>
      {f.thumb ? <img className="dtthumb" src={f.thumb} alt="" /> : <span className="dtthumb">📄</span>}
      <div className="dtmain"><b>{f.name}</b><span className="small muted">{f.by} · {new Date(f.created_at).toLocaleDateString('ru-RU')}</span></div>
    </div>)}
    <Viewer f={open} onClose={() => setOpen(null)} /></>
}

// Блок «Дизайн» в карточке сделки (МОП и HEAD): список задач и кнопка «Нужен дизайн».
export function DealDesign({ dealId }) {
  const [d, setD] = useState(null)
  const [add, setAdd] = useState(null)
  const [err, setErr] = useState('')
  const load = () => api(`/bx/deals/${dealId}/design-tasks`).then(setD, () => setD({ items: [], can_add: false, off: true }))
  useEffect(() => { load() }, [dealId])
  if (!d || d.off || (!d.can_add && !d.items.length)) return null
  const send = () => { setErr(''); api(`/bx/deals/${dealId}/design-tasks`, { method: 'POST', body: { title: add.title.trim(), note: add.note.trim() || null, urgent: add.urgent } })
    .then(() => { setAdd(null); load() }, e => setErr(e.message)) }
  const drop = t => api(`/design/tasks/${t.id}/cancel`, { method: 'POST' }).then(load, e => setErr(e.message))
  return <div className="card dtdeal">
    <div className="head"><h3>Дизайн</h3>{!!d.items.length && <span className="badge">{d.items.length}</span>}</div>
    {d.items.map(t => <div key={t.id} className="dtrow">
      <div className="dtmain"><b>{t.title}</b><span className="small muted">{who(t)}</span></div>
      <span className={'tag' + tone(t.stage)}>{t.stage_name}</span>
      {d.can_add && t.stage === 'new' && <button className="pencil" aria-label="Убрать задачу" onClick={() => drop(t)}>✕</button>}
    </div>)}
    {!d.items.length && <p className="small muted">Задач на дизайн по этой сделке пока нет.</p>}
    <SeeFiles dealId={dealId} />
    {d.can_add && <button onClick={() => setAdd({ title: '', note: '', urgent: false })}>+ Нужен дизайн</button>}
    {d.can_add && <p className="small muted">Сделка остаётся на своей стадии. Дизайнер увидит задачу у себя во вкладке «Дизайн».</p>}
    {err && !add && <p className="small why">{err}</p>}
    {add && <Sheet title="Нужен дизайн" onClose={() => setAdd(null)}>
      <label>Что рисуем</label>
      <input value={add.title} maxLength={120} placeholder="Например: столовая" onChange={e => setAdd({ ...add, title: e.target.value })} />
      <label>Задача дизайнеру</label>
      <textarea rows={3} value={add.note} maxLength={1000} placeholder="Размер стены, тема, пожелания клиента" onChange={e => setAdd({ ...add, note: e.target.value })} />
      <label className="dtcheck"><input type="checkbox" checked={add.urgent} onChange={e => setAdd({ ...add, urgent: e.target.checked })} /> Срочно</label>
      {err && <p className="small why">{err}</p>}
      <button disabled={add.title.trim().length < 2} onClick={send}>Отправить дизайнеру</button>
    </Sheet>}
  </div>
}

// Сколько открытых задач у дизайнера — чтобы «Дизайн» сразу открывал доску, когда на ней что-то есть.
export function useTaskCount() {
  const [n, setN] = useState(null)
  useEffect(() => { api('/design/tasks').then(d => setN(d.items.filter(t => t.stage !== 'done').length), () => setN(0)) }, [])
  return n
}

// Доска дизайнера: задачи по стадиям. Дизайнер видит свои и неразобранные, Главный и HEAD — все.
export function TaskBoard({ team, me }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [only, setOnly] = useState('')
  const [open, setOpen] = useState(null)
  const load = () => api('/design/tasks').then(setD, e => setErr(e.message))
  useEffect(() => { load() }, [])
  if (err) return <div className="card"><p className="small why">{err}</p></div>
  if (!d) return <div className="card"><p className="muted">Загружаю…</p></div>
  const live = d.items.filter(t => t.stage !== 'done')
  const order = ['urgent', 'work', 'fix', 'info', 'new', 'wait', 'mop', 'done']
  const name = Object.fromEntries(d.stages.map(s => [s.id, s.name]))
  const groups = order.map(k => [k, d.items.filter(t => t.stage === k)]).filter(([k, rows]) => rows.length && (!only || only === k))
  const late = t => t.deadline && t.stage !== 'done' && t.deadline < today()
  return <>
    <div className="card"><div className="head"><h2>{d.all ? 'Задачи на дизайн' : 'Мои задачи'} <span className="muted small">{live.length}</span></h2>
      <button className="ghost mini" onClick={() => { setD(null); load() }}>Обновить</button></div>
      <p className="small muted">Задачи приходят из карточек сделок, когда МОП жмёт «Нужен дизайн». Сделка при этом стоит на своей стадии. Единица — одна за весь проект.</p></div>
    {!!d.items.length && <div className="chips scroll">
      <button className={!only ? 'on' : ''} onClick={() => setOnly('')}>Все <span>{live.length}</span></button>
      {order.filter(k => d.items.some(t => t.stage === k)).map(k => <button key={k} className={only === k ? 'on' : ''} onClick={() => setOnly(only === k ? '' : k)}>{name[k]} <span>{d.items.filter(t => t.stage === k).length}</span></button>)}
    </div>}
    {groups.map(([k, rows]) => <div key={k} className={'card dtstage ' + k}>
      <p className="dtcap">{name[k]}</p>
      {rows.map(t => <div key={t.id} className="dtrow click" onClick={() => setOpen(t)}>
        <div className="dtmain"><b>№ {t.deal_id} {cleanTitle(t.deal_title, t.deal_id)} · {t.title}</b>
          <span className="small muted">{[t.city, t.size ? t.size.toUpperCase() : '', t.deadline ? 'срок ' + dm(t.deadline) : '', d.all ? (t.designer || 'не назначен') : (t.designer_id ? '' : 'свободна'), k === 'new' && t.note ? `«${t.note}»` : ''].filter(Boolean).join(' · ')}</span></div>
        {late(t) ? <span className="tag hott">просрочена</span> : t.deadline === today() ? <span className="tag hott">сегодня</span> : k === 'new' ? <span className="tag none">новая</span> : null}
      </div>)}
    </div>)}
    {!d.items.length && <div className="card"><p className="small muted">Задач пока нет. Они появятся здесь, когда МОП нажмёт «Нужен дизайн» в карточке сделки.</p></div>}
    {open && <TaskSheet t={open} d={d} team={team} me={me} onClose={() => setOpen(null)} onDone={x => { setOpen(x || null); load() }} />}
  </>
}

function TaskSheet({ t, d, team, me, onClose, onDone }) {
  const [err, setErr] = useState('')
  const save = (body, close) => { setErr(''); return api(`/design/tasks/${t.id}`, { method: 'POST', body }).then(x => onDone(close ? null : x), e => setErr(e.message)) }
  const mine = d.all || !t.designer_id || t.designer_id === d.me
  const designers = (team || []).filter(x => x.id)
  return <Sheet title={`№ ${t.deal_id} · ${t.title}`} onClose={onClose}>
    <p className="small muted">{cleanTitle(t.deal_title, t.deal_id)}{t.city && !t.deal_title.includes(t.city) ? ' — ' + t.city : ''} · задача от {t.by}</p>
    {t.note && <p className="small">«{t.note}»</p>}
    <label>Стадия</label>
    <select value={t.stage} disabled={!mine} onChange={e => save({ stage: e.target.value })}>{d.stages.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
    {d.all ? <><label>Дизайнер</label>
      <select value={t.designer_id || ''} onChange={e => save({ designer_id: +e.target.value || null })}><option value="">не назначен</option>{designers.map(x => <option key={x.id} value={x.id}>{x.full_name}</option>)}</select></>
      : !t.designer_id && <button className="ghost" onClick={() => save({ designer_id: d.me, stage: t.stage === 'new' ? 'work' : t.stage })}>Беру в работу</button>}
    <div className="dttwo"><div><label>Размер</label>
      <select value={t.size} disabled={!mine} onChange={e => save({ size: e.target.value || null })}><option value="">—</option>{d.sizes.map(s => <option key={s} value={s}>{s.toUpperCase()}</option>)}</select></div>
      <div><label>Срок</label><input type="date" value={t.deadline} disabled={!mine} onChange={e => save({ deadline: e.target.value || null })} /></div></div>
    <h3 className="dth">Эскизы и материалы</h3>
    <p className="small muted">Загрузите файл — он сам ляжет в папку сделки «ДИЗАЙН». МОП увидит его в карточке сделки.</p>
    <DealFiles dealId={t.deal_id} me={me} />
    {err && <p className="small why">{err}</p>}
    <div className="dttwo dtacts">
      {t.bitrix ? <button className="ghost" onClick={() => openUrl(t.bitrix)}>Написать клиенту</button> : <span />}
      {mine && t.stage !== 'wait' && t.stage !== 'done' && <button className="ghost" onClick={() => save({ stage: 'wait' })}>Жду клиента</button>}
    </div>
    {mine && t.stage !== 'done' && <button className="okbtn" onClick={() => save({ stage: 'done' }, true)}>Утверждено</button>}
    <p className="small muted">«Написать клиенту» открывает сделку в Битриксе. После «Утверждено» МОП видит эскиз в карточке сделки. Единица считается одна за весь проект.</p>
  </Sheet>
}

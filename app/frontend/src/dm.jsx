import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { FeedbackInbox } from './feedback.jsx'

// «Чат» (HEAD 11.11): у сотрудника — 📣 Объявления, 🏢 Руководство (видят все HEAD), 👤 личный чат с каждым HEAD.
// У каждого HEAD одинаково: Руководство (+ обращения), свои личные чаты, Объявления («Написать всем»). В бот — только объявления.
const when = s => {
  const d = new Date(s), now = new Date()
  const t = d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  return d.toDateString() === now.toDateString() ? t : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) + ' ' + t
}

// непрочитанные для цифры на вкладке: раз в минуту и когда приложение снова на экране
const READ = 'artgame:dm-read'   // диалог открыт и прочитан — цифру обновить сразу
export function useUnread(tab) {
  const [n, setN] = useState(0)
  useEffect(() => {
    const load = () => api('/dm/unread').then(r => setN(r.n), () => {})
    load()
    window.addEventListener(READ, load)
    const t = setInterval(load, 60000)
    const vis = () => document.visibilityState === 'visible' && load()
    document.addEventListener('visibilitychange', vis)
    return () => { clearInterval(t); document.removeEventListener('visibilitychange', vis); window.removeEventListener(READ, load) }
  }, [tab])
  return n
}

function Bubbles({ items, mine, names }) {
  const end = useRef(null)
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }) }, [items.length])
  if (!items.length) return <p className="small muted dmempty">Сообщений пока нет.</p>
  return <div className="dmlist">
    {items.map(m => <div key={m.id} className={'dmb ' + (mine(m) ? 'me' : 'them')}>
      {m.broadcast && <span className="dmcast">📣 объявление</span>}
      <div className="dmtext">{m.text}</div>
      <span className="dmmeta">{m.from_head && (names || !mine(m)) ? m.author + ' · ' : ''}{when(m.created_at)}{m.via === 'tg' ? ' · из Telegram' : ''}</span>
    </div>)}
    <div ref={end} />
  </div>
}

function Composer({ send, ph }) {
  const [v, set] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const go = () => {
    if (!v.trim()) return
    setBusy(true); setErr('')
    send(v.trim()).then(() => set(''), e => setErr(e.message)).finally(() => setBusy(false))
  }
  return <div className="dmform">
    <textarea rows={3} placeholder={ph} value={v} onChange={e => set(e.target.value)} />
    <button disabled={busy || !v.trim()} onClick={go}>{busy ? 'Отправляю…' : 'Отправить'}</button>
    {err && <p className="small why">{err}</p>}
  </div>
}

const ICON = { news: '📣', group: '🏢', head: '👤' }
const cnt = n => +n > 0 ? <i className="cnt dmcnt">{n}</i> : null
const done = () => window.dispatchEvent(new Event(READ))

// ---------- сотрудник ----------
export function DialogHead() {
  const [rooms, setRooms] = useState(null)
  const [open, setOpen] = useState(null)
  const load = () => api('/dm/rooms').then(r => setRooms(r.rooms), () => setRooms([]))
  useEffect(() => { load() }, [])
  if (open) return <Room r={open} back={() => { setOpen(null); load() }} />
  return <div className="card dm">
    <h2>Чат</h2>
    <p className="small muted">Объявления — от HEAD всем. «Руководство» видят все HEAD. Личный чат видите только вы двое.</p>
    {rooms === null ? <p className="small muted">Загрузка…</p> : rooms.map(r => <div key={r.key} className="qrow dmrow" onClick={() => setOpen(r)}>
      <span className="ic dmic">{ICON[r.kind]}</span>
      <div className="qmain"><b>{r.title}</b>{cnt(r.unread)}
        <div className="small muted">{r.about}{r.last_at ? ' · ' + when(r.last_at) : ''}</div>
        {r.last_text && <div className={'small dmlast' + (+r.unread ? ' new' : '')}>{r.last_text}</div>}
      </div><span className="muted">›</span>
    </div>)}
  </div>
}

function Room({ r, back }) {
  const [items, setItems] = useState(null)
  const load = () => api(`/dm/room/${r.key}`).then(x => { setItems(x.items); done() }, () => setItems([]))
  useEffect(() => { load() }, [r.key])
  const who = r.kind === 'group' ? 'Увидит всё руководство (все HEAD)' : r.kind === 'head' ? `Увидит только ${r.title}` : ''
  return <div className="card dm">
    <button className="ghost mini dmback" onClick={back}>‹ Все чаты</button>
    <h2>{ICON[r.kind]} {r.title}</h2><p className="small muted">{r.about}</p>
    {items === null ? <p className="small muted">Загрузка…</p> : <Bubbles items={items} mine={m => !m.from_head} names />}
    {r.kind === 'news' ? <p className="small muted">Ответить на объявление можно в «Руководство» или лично HEAD.</p> : <>
      <p className="small dmwho">{who}</p>
      <Composer ph={r.kind === 'group' ? 'Написать руководству' : `Написать: ${r.title}`}
        send={text => api(`/dm/room/${r.key}`, { method: 'POST', body: { text } }).then(load)} /></>}
  </div>
}

// ---------- HEAD (любой HEAD одинаково) ----------
export function Messages() {
  const [d, setD] = useState(null)
  const [seg, setSeg] = useState('group')
  const [open, setOpen] = useState(null)   // {pid, room} или 'all'
  const [fb, setFb] = useState(null)
  const load = () => { api('/dm/threads').then(setD, e => setD({ err: e.message }))
    api('/feedback').then(r => setFb(r.items.filter(f => f.status !== 'done')), () => setFb([])) }
  useEffect(() => { load() }, [])
  if (open === 'all') return <Broadcast roles={d?.roles || []} back={() => { setOpen(null); load() }} />
  if (open) return <HeadDialog pid={open.pid} room={open.room} back={() => { setOpen(null); load() }} />
  if (!d) return <div className="card muted">Загрузка…</div>
  if (d.err) return <div className="card muted">{d.err}</div>
  const ug = d.group.reduce((n, x) => n + +x.unread, 0), um = d.items.reduce((n, x) => n + +x.unread, 0)
  const list = (rows, room) => rows.map(x => <div key={x.id} className="qrow dmrow" onClick={() => setOpen({ pid: x.id, room })}>
    <div className="qmain"><b>{x.full_name}</b>{cnt(x.unread)}
      <div className="small muted">{x.role_title}{x.last_at ? ' · ' + when(x.last_at) : ''}</div>
      {x.last_text && <div className={'small dmlast' + (+x.unread ? ' new' : '')}>{x.last_from_head ? (x.last_author || 'HEAD') + ': ' : ''}{x.last_text}</div>}
    </div><span className="muted">›</span></div>)
  return <>
    <div className="card dm">
      <h2>Чат</h2>
      <div className="segf dmseg">
        <button className={seg === 'group' ? 'on' : ''} onClick={() => setSeg('group')}>Руководство{cnt(ug + (fb?.length || 0))}</button>
        <button className={seg === 'me' ? 'on' : ''} onClick={() => setSeg('me')}>Личные{cnt(um)}</button>
        <button className={seg === 'news' ? 'on' : ''} onClick={() => setSeg('news')}>Объявления</button>
      </div>
      <p className="small muted">{seg === 'group' ? 'Видят и отвечают все HEAD. Под ответом — кто ответил.' :
        seg === 'me' ? 'Ваши личные чаты. Другие HEAD их не видят. Можно написать первым.' : 'Всем или по ролям. Приходит в приложение и в бот.'}</p>
      {seg === 'news' && <button onClick={() => setOpen('all')}>📣 Написать всем</button>}
    </div>
    {seg === 'group' && <>
      {fb?.length > 0 && <FeedbackInbox items={fb} reload={load} />}
      <div className="card dm">{d.group.length ? list(d.group, 'group') : <p className="small muted">В «Руководство» пока не писали.</p>}</div></>}
    {seg === 'me' && <div className="card dm">{d.items.length ? list(d.items, 'me') : <p className="small muted">Активных сотрудников пока нет.</p>}</div>}
    {seg === 'news' && d.broadcasts.length > 0 && <div className="card dm"><h3>Отправленные</h3>
      {d.broadcasts.map(b => <div key={b.id} className="dmcastrow">
        <div className="small muted">{when(b.created_at)} · {b.author} · {b.roles?.length ? b.roles.map(r => d.roles.find(x => x.code === r)?.title || r).join(', ') : 'всем'} · получили {b.sent}</div>
        <div className="dmtext">{b.text}</div></div>)}
    </div>}
  </>
}

function HeadDialog({ pid, room, back }) {
  const [d, setD] = useState(null)
  const load = () => api(`/dm/with/${pid}?room=${room}`).then(r => { setD(r); done() }, e => setD({ err: e.message }))
  useEffect(() => { load() }, [pid, room])
  return <div className="card dm">
    <button className="ghost mini dmback" onClick={back}>‹ Все чаты</button>
    {!d ? <p className="small muted">Загрузка…</p> : d.err ? <p className="small muted">{d.err}</p> : <>
      <h2>{d.person.full_name}</h2><p className="small muted">{d.person.role_title} · {room === 'group' ? '🏢 Руководство' : '👤 личный чат'}</p>
      <Bubbles items={d.items} mine={m => m.from_head} names={room === 'group'} />
      {d.person.status === 'active' ? <>
        <p className="small dmwho">{room === 'group' ? 'Ответ увидят сотрудник и все HEAD' : `Увидит только ${d.person.full_name}`}</p>
        <Composer ph={`Написать: ${d.person.full_name}`}
          send={text => api(`/dm/with/${pid}?room=${room}`, { method: 'POST', body: { text } }).then(load)} /></> :
        <p className="small muted">Вход сотрудника закрыт — написать нельзя.</p>}
    </>}
  </div>
}

function Broadcast({ roles, back }) {
  const [pick, setPick] = useState([])
  const [ok, setOk] = useState('')
  const total = roles.reduce((n, r) => n + +r.n, 0)
  const flip = c => setPick(pick.includes(c) ? pick.filter(x => x !== c) : [...pick, c])
  return <div className="card dm">
    <button className="ghost mini dmback" onClick={back}>‹ Все чаты</button>
    <h2>Написать всем</h2>
    <p className="small muted">Кому: всем или выберите роли. Придёт в «Объявления» и в бот Telegram, с вашим именем.</p>
    <div className="chips">
      <button className={pick.length ? '' : 'on'} onClick={() => setPick([])}>Всем<span>{total}</span></button>
      {roles.map(r => <button key={r.code} className={pick.includes(r.code) ? 'on' : ''} onClick={() => flip(r.code)}>{r.title}<span>{r.n}</span></button>)}
    </div>
    {ok ? <><p className="small ok">{ok}</p><button className="ghost" onClick={back}>Готово</button></> :
      <Composer ph="Текст объявления"
        send={text => api('/dm/broadcast', { method: 'POST', body: { text, roles: pick.length ? pick : null } }).then(r => setOk(`Отправлено: ${r.sent} чел.`))} />}
  </div>
}

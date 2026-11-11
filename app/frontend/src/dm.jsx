import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { FeedbackInbox } from './feedback.jsx'

// «Чат» (HEAD 11.11): «HEAD» — объявления + вопросы руководству (видят все HEAD); личные чаты любой ↔ любой (видят двое).
// В бот — только объявления.
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

const cnt = n => +n > 0 ? <i className="cnt dmcnt">{n}</i> : null
const done = () => window.dispatchEvent(new Event(READ))
const initials = n => (n || '?').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase()

// Один экран «Чат» у всех (HEAD 11.11, как в Telegram): сверху «HEAD» — объявления и вопросы руководству;
// ниже — личные чаты с любым человеком команды (видят только двое). Поиск по имени.
export function Chat({ head }) {
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(null)   // 'hq' | {id, full_name}
  const [q, setQ] = useState('')
  const load = () => api('/dm/list').then(setD, e => setD({ err: e.message }))
  useEffect(() => { load() }, [])
  const back = () => { setOpen(null); load() }
  if (open === 'hq') return head ? <HeadInbox back={back} /> : <HqRoom back={back} />
  if (open) return <Pm who={open} back={back} />
  if (!d) return <div className="card muted">Загрузка…</div>
  if (d.err) return <div className="card muted">{d.err}</div>
  const ql = q.trim().toLowerCase()
  const people = d.people.filter(x => !ql || x.full_name.toLowerCase().includes(ql) || (x.role_title || '').toLowerCase().includes(ql))
  const talk = people.filter(x => x.last_at), rest = people.filter(x => !x.last_at)
  const row = x => <div key={x.id} className="qrow dmrow" onClick={() => setOpen(x)}>
    <span className={'ic dmav' + (x.role_code === 'head' ? ' head' : '')}>{initials(x.full_name)}</span>
    <div className="qmain"><b>{x.full_name}</b>{cnt(x.unread)}
      <div className="small muted">{x.role_title}{x.last_at ? ' · ' + when(x.last_at) : ''}</div>
      {x.last_text && <div className={'small dmlast' + (+x.unread ? ' new' : '')}>{x.last_mine ? 'Вы: ' : ''}{x.last_text}</div>}
    </div><span className="muted">›</span></div>
  return <>
    <div className="card dm">
      <h2>Чат</h2>
      <div className="qrow dmrow dmhq" onClick={() => setOpen('hq')}>
        <span className="ic dmav hq">HEAD</span>
        <div className="qmain"><b>HEAD</b>{cnt(d.hq.unread)}
          <div className="small muted">{head ? 'вопросы команды и объявления · видят все HEAD' : 'объявления и вопросы руководству'}{d.hq.last_at ? ' · ' + when(d.hq.last_at) : ''}</div>
          {d.hq.last_text && <div className={'small dmlast' + (+d.hq.unread ? ' new' : '')}>{d.hq.last_text}</div>}
        </div><span className="muted">›</span></div>
    </div>
    <div className="card dm">
      <h3>Личные</h3>
      <input className="dmsearch" placeholder="Найти по имени или роли" value={q} onChange={e => setQ(e.target.value)} />
      {talk.map(row)}
      {talk.length > 0 && rest.length > 0 && <p className="small muted dmsub">Написать</p>}
      {rest.map(row)}
      {!people.length && <p className="small muted">Никого не нашлось.</p>}
      <p className="small muted dmsub">Личный чат видите только вы двое.</p>
    </div>
  </>
}

// сотрудник: чат «HEAD» — объявления и свои вопросы руководству
function HqRoom({ back }) {
  const [items, setItems] = useState(null)
  const load = () => api('/dm/room/hq').then(x => { setItems(x.items); done() }, () => setItems([]))
  useEffect(() => { load() }, [])
  return <div className="card dm">
    <button className="ghost mini dmback" onClick={back}>‹ Все чаты</button>
    <h2>HEAD</h2><p className="small muted">Объявления руководства и твои вопросы. Отвечает любой HEAD.</p>
    {items === null ? <p className="small muted">Загрузка…</p> : <Bubbles items={items} mine={m => !m.from_head} names />}
    <p className="small dmwho">Увидит руководство (все HEAD). Другие сотрудники не видят.</p>
    <Composer ph="Написать руководству" send={text => api('/dm/room/hq', { method: 'POST', body: { text } }).then(load)} />
  </div>
}

// личный чат двоих
function Pm({ who, back }) {
  const [d, setD] = useState(null)
  const load = () => api(`/dm/pm/${who.id}`).then(r => { setD(r); done() }, e => setD({ err: e.message }))
  useEffect(() => { load() }, [who.id])
  return <div className="card dm">
    <button className="ghost mini dmback" onClick={back}>‹ Все чаты</button>
    <h2>{who.full_name}</h2><p className="small muted">{who.role_title} · личный чат</p>
    {!d ? <p className="small muted">Загрузка…</p> : d.err ? <p className="small muted">{d.err}</p> : <>
      <Bubbles items={d.items} mine={m => m.mine} />
      {d.person.status === 'active' ? <>
        <p className="small dmwho">Увидит только {who.full_name}</p>
        <Composer ph={`Написать: ${who.full_name}`} send={text => api(`/dm/pm/${who.id}`, { method: 'POST', body: { text } }).then(load)} /></> :
        <p className="small muted">Вход закрыт — написать нельзя.</p>}
    </>}
  </div>
}

// HEAD: чат «HEAD» — кто спрашивал, обращения, «Написать всем»
function HeadInbox({ back }) {
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(null)
  const [fb, setFb] = useState(null)
  const load = () => { api('/dm/threads').then(setD, e => setD({ err: e.message }))
    api('/feedback').then(r => setFb(r.items.filter(f => f.status !== 'done')), () => setFb([])) }
  useEffect(() => { load() }, [])
  if (open === 'all') return <Broadcast roles={d?.roles || []} back={() => { setOpen(null); load() }} />
  if (open) return <HeadDialog pid={open} back={() => { setOpen(null); load() }} />
  return <>
    <div className="card dm">
      <button className="ghost mini dmback" onClick={back}>‹ Все чаты</button>
      <h2>HEAD</h2>
      <p className="small muted">Вопросы команды руководству и ваши объявления. Видят и отвечают все HEAD, под ответом — кто ответил.</p>
      <button onClick={() => setOpen('all')}>📣 Написать всем</button>
    </div>
    {fb?.length > 0 && <FeedbackInbox items={fb} reload={load} />}
    {!d ? <div className="card muted">Загрузка…</div> : d.err ? <div className="card muted">{d.err}</div> : <>
      <div className="card dm"><h3>Вопросы</h3>
        {d.group.length ? d.group.map(x => <div key={x.id} className="qrow dmrow" onClick={() => setOpen(x.id)}>
          <div className="qmain"><b>{x.full_name}</b>{cnt(x.unread)}
            <div className="small muted">{x.role_title}{x.last_at ? ' · ' + when(x.last_at) : ''}</div>
            {x.last_text && <div className={'small dmlast' + (+x.unread ? ' new' : '')}>{x.last_from_head ? (x.last_author || 'HEAD') + ': ' : ''}{x.last_text}</div>}
          </div><span className="muted">›</span></div>) : <p className="small muted">Вопросов пока нет.</p>}
      </div>
      {d.broadcasts.length > 0 && <div className="card dm"><h3>Объявления</h3>
        {d.broadcasts.map(b => <div key={b.id} className="dmcastrow">
          <div className="small muted">{when(b.created_at)} · {b.author} · {b.roles?.length ? b.roles.map(r => d.roles.find(x => x.code === r)?.title || r).join(', ') : 'всем'} · получили {b.sent}</div>
          <div className="dmtext">{b.text}</div></div>)}
      </div>}
    </>}
  </>
}

function HeadDialog({ pid, back }) {
  const [d, setD] = useState(null)
  const load = () => api(`/dm/with/${pid}`).then(r => { setD(r); done() }, e => setD({ err: e.message }))
  useEffect(() => { load() }, [pid])
  return <div className="card dm">
    <button className="ghost mini dmback" onClick={back}>‹ Чат HEAD</button>
    {!d ? <p className="small muted">Загрузка…</p> : d.err ? <p className="small muted">{d.err}</p> : <>
      <h2>{d.person.full_name}</h2><p className="small muted">{d.person.role_title} · чат «HEAD»</p>
      <Bubbles items={d.items} mine={m => m.from_head} names />
      {d.person.status === 'active' ? <>
        <p className="small dmwho">Ответ увидят {d.person.full_name} и все HEAD</p>
        <Composer ph={`Ответить: ${d.person.full_name}`}
          send={text => api(`/dm/with/${pid}`, { method: 'POST', body: { text } }).then(load)} /></> :
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
    <button className="ghost mini dmback" onClick={back}>‹ Чат HEAD</button>
    <h2>Написать всем</h2>
    <p className="small muted">Кому: всем или выберите роли. Придёт каждому в чат «HEAD» и в бот Telegram, с вашим именем.</p>
    <div className="chips">
      <button className={pick.length ? '' : 'on'} onClick={() => setPick([])}>Всем<span>{total}</span></button>
      {roles.map(r => <button key={r.code} className={pick.includes(r.code) ? 'on' : ''} onClick={() => flip(r.code)}>{r.title}<span>{r.n}</span></button>)}
    </div>
    {ok ? <><p className="small ok">{ok}</p><button className="ghost" onClick={back}>Готово</button></> :
      <Composer ph="Текст объявления"
        send={text => api('/dm/broadcast', { method: 'POST', body: { text, roles: pick.length ? pick : null } }).then(r => setOk(`Отправлено: ${r.sent} чел.`))} />}
  </div>
}

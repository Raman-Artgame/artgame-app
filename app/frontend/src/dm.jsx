import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'

// «Диалог с HEAD» (HEAD 09.11): у сотрудника вкладка «HEAD» — личный диалог; у HEAD «Ещё → Сообщения» —
// все диалоги и «Написать всем» (всем или по ролям). В бот уходит только рассылка HEAD; личные — только здесь (HEAD 10.11).
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

function Bubbles({ items, mine }) {
  const end = useRef(null)
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }) }, [items.length])
  if (!items.length) return <p className="small muted dmempty">Сообщений пока нет.</p>
  return <div className="dmlist">
    {items.map(m => <div key={m.id} className={'dmb ' + (mine(m) ? 'me' : 'them')}>
      {m.broadcast && <span className="dmcast">📣 рассылка</span>}
      <div className="dmtext">{m.text}</div>
      <span className="dmmeta">{!mine(m) && m.from_head ? m.author + ' · ' : ''}{when(m.created_at)}{m.via === 'tg' ? ' · из Telegram' : ''}</span>
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

// сотрудник: один диалог с HEAD
export function DialogHead() {
  const [items, setItems] = useState(null)
  const load = () => api('/dm').then(r => { setItems(r.items); window.dispatchEvent(new Event(READ)) }, () => setItems([]))
  useEffect(() => { load() }, [])
  return <div className="card dm">
    <h2>Диалог с HEAD</h2>
    <p className="small muted">Пиши по делу: вопрос, проблема на объекте, предложение. Ответ придёт сюда.</p>
    {items === null ? <p className="small muted">Загрузка…</p> : <Bubbles items={items} mine={m => !m.from_head} />}
    <Composer ph="Написать HEAD" send={text => api('/dm', { method: 'POST', body: { text } }).then(load)} />
  </div>
}

// HEAD: список диалогов, личный диалог, рассылка
export function Messages() {
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(null)   // id сотрудника или 'all'
  const load = () => api('/dm/threads').then(setD, e => setD({ err: e.message }))
  useEffect(() => { load() }, [])
  if (open === 'all') return <Broadcast roles={d?.roles || []} back={() => { setOpen(null); load() }} />
  if (open) return <HeadDialog pid={open} back={() => { setOpen(null); load() }} />
  if (!d) return <div className="card muted">Загрузка…</div>
  if (d.err) return <div className="card muted">{d.err}</div>
  const unread = d.items.reduce((n, x) => n + +x.unread, 0)
  return <>
    <div className="card dm">
      <div className="head"><div><h2>Сообщения</h2><p className="small muted">{unread ? `Новых: ${unread}` : 'Новых нет'} · сотрудник видит диалог во вкладке «HEAD»</p></div></div>
      <button onClick={() => setOpen('all')}>📣 Написать всем</button>
    </div>
    <div className="card dm">
      {d.items.length === 0 && <p className="small muted">Активных сотрудников пока нет.</p>}
      {d.items.map(x => <div key={x.id} className="qrow dmrow" onClick={() => setOpen(x.id)}>
        <div className="qmain"><b>{x.full_name}</b>{x.unread > 0 && <i className="cnt dmcnt">{x.unread}</i>}
          <div className="small muted">{x.role_title}{x.last_at ? ' · ' + when(x.last_at) : ''}</div>
          {x.last_text && <div className={'small dmlast' + (x.unread > 0 ? ' new' : '')}>{x.last_from_head ? 'Вы: ' : ''}{x.last_text}</div>}
        </div><span className="muted">›</span>
      </div>)}
    </div>
    {d.broadcasts.length > 0 && <div className="card dm"><h3>Рассылки</h3>
      {d.broadcasts.map(b => <div key={b.id} className="dmcastrow">
        <div className="small muted">{when(b.created_at)} · {b.roles?.length ? b.roles.map(r => d.roles.find(x => x.code === r)?.title || r).join(', ') : 'всем'} · получили {b.sent}</div>
        <div className="dmtext">{b.text}</div></div>)}
    </div>}
  </>
}

function HeadDialog({ pid, back }) {
  const [d, setD] = useState(null)
  const load = () => api(`/dm/with/${pid}`).then(r => { setD(r); window.dispatchEvent(new Event(READ)) }, e => setD({ err: e.message }))
  useEffect(() => { load() }, [pid])
  return <div className="card dm">
    <button className="ghost mini dmback" onClick={back}>‹ Все диалоги</button>
    {!d ? <p className="small muted">Загрузка…</p> : d.err ? <p className="small muted">{d.err}</p> : <>
      <h2>{d.person.full_name}</h2><p className="small muted">{d.person.role_title}</p>
      <Bubbles items={d.items} mine={m => m.from_head} />
      {d.person.status === 'active' ? <Composer ph={`Написать: ${d.person.full_name}`}
        send={text => api(`/dm/with/${pid}`, { method: 'POST', body: { text } }).then(load)} /> :
        <p className="small muted">Вход сотрудника закрыт — написать нельзя.</p>}
    </>}
  </div>
}

function Broadcast({ roles, back }) {
  const [pick, setPick] = useState([])
  const [done, setDone] = useState('')
  const total = roles.reduce((n, r) => n + +r.n, 0)
  const flip = c => setPick(pick.includes(c) ? pick.filter(x => x !== c) : [...pick, c])
  return <div className="card dm">
    <button className="ghost mini dmback" onClick={back}>‹ Все диалоги</button>
    <h2>Написать всем</h2>
    <p className="small muted">Кому: всем или выберите роли. Каждый получит сообщение в своём диалоге «HEAD» и в боте Telegram. Личные сообщения в бот не уходят.</p>
    <div className="chips">
      <button className={pick.length ? '' : 'on'} onClick={() => setPick([])}>Всем<span>{total}</span></button>
      {roles.map(r => <button key={r.code} className={pick.includes(r.code) ? 'on' : ''} onClick={() => flip(r.code)}>{r.title}<span>{r.n}</span></button>)}
    </div>
    {done ? <><p className="small ok">{done}</p><button className="ghost" onClick={back}>Готово</button></> :
      <Composer ph="Текст для всех выбранных"
        send={text => api('/dm/broadcast', { method: 'POST', body: { text, roles: pick.length ? pick : null } }).then(r => setDone(`Отправлено: ${r.sent} чел.`))} />}
  </div>
}

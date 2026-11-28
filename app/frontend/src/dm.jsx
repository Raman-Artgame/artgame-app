import React, { useEffect, useRef, useState } from 'react'
import { api, uuid } from './api.js'
import { FeedbackInbox } from './feedback.jsx'
import { shrink } from './work.jsx'

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

// HEAD 20.11: «не могу скопировать сообщение» — в Telegram на iPhone выделение текста в приложении не работает.
// Долгое нажатие (или правая кнопка) на сообщении → «Скопировать»; копируем через буфер обмена, запасной путь — execCommand.
export async function copyText(t) {
  try { await navigator.clipboard.writeText(t); return true } catch { /* ниже */ }
  try {
    const a = document.createElement('textarea'); a.value = t; a.setAttribute('readonly', ''); a.style.position = 'fixed'; a.style.opacity = '0'
    document.body.appendChild(a); a.select(); a.setSelectionRange(0, t.length); const ok = document.execCommand('copy'); a.remove(); return ok
  } catch { return false }
}
export function Msg({ text }) {
  const [menu, setMenu] = useState('')   // '' | 'ask' | 'ok' | 'fail'
  const t = useRef(null), at = useRef(null)
  const stop = () => { clearTimeout(t.current); t.current = null }
  const down = e => { const p = e.touches?.[0] || e; at.current = [p.clientX, p.clientY]; stop(); t.current = setTimeout(() => { t.current = null; setMenu('ask') }, 450) }
  const move = e => { const p = e.touches?.[0] || e; if (at.current && Math.hypot(p.clientX - at.current[0], p.clientY - at.current[1]) > 10) stop() }
  const copy = async e => { e.stopPropagation(); const ok = await copyText(text); setMenu(ok ? 'ok' : 'fail'); setTimeout(() => setMenu(''), 1500) }
  useEffect(() => stop, [])
  return <div className="dmtext" onTouchStart={down} onTouchMove={move} onTouchEnd={stop} onTouchCancel={stop}
    onContextMenu={e => { e.preventDefault(); setMenu('ask') }}>
    {text}
    {menu && <div className="dmcopy" onClick={e => e.stopPropagation()}>
      {menu === 'ask' ? <><button className="mini" onClick={copy}>⧉ Скопировать</button><button className="ghost mini" onClick={() => setMenu('')}>✕</button></>
        : <span className="small">{menu === 'ok' ? '✓ Скопировано' : 'Не получилось скопировать'}</span>}</div>}
  </div>
}

function Bubbles({ items, mine, names }) {
  const end = useRef(null)
  useEffect(() => { end.current?.scrollIntoView?.({ block: 'end' }) }, [items.length])
  if (!items.length) return <p className="small muted dmempty">Сообщений пока нет.</p>
  return <div className="dmlist">
    {items.map(m => <div key={m.id} className={'dmb ' + (mine(m) ? 'me' : 'them')}>
      {m.broadcast && <span className="dmcast">📣 объявление</span>}
      <Att file={m.file} />
      {m.text && <Msg text={m.text} />}
      <span className="dmmeta">{m.from_head && (names || !mine(m)) ? m.author + ' · ' : ''}{when(m.created_at)}{m.via === 'tg' ? ' · из Telegram' : ''}</span>
    </div>)}
    <div ref={end} />
  </div>
}

// Вложение в сообщении (HEAD 24.11: «в чаты нужно добавить функцию прикрепления файлов и фото»)
const MAX_FILE = 20 * 1024 * 1024
const fsize = n => n >= 1048576 ? (n / 1048576).toFixed(1).replace('.', ',') + ' МБ' : Math.max(1, Math.round(n / 1024)) + ' КБ'
const fext = n => { const m = /\.([A-Za-zА-Яа-я0-9]{1,5})$/.exec(n || ''); return m ? m[1].toUpperCase() : 'ФАЙЛ' }
const readUrl = f => new Promise((ok, bad) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => bad(new Error('Файл не прочитался, выбери его ещё раз')); r.readAsDataURL(f) })
export function Att({ file }) {
  if (!file) return null
  if (file.thumb) return <a href={file.url} target="_blank" rel="noreferrer"><img loading="lazy" className="dmpic" src={file.thumb} alt={file.name} /></a>
  return <a className="dmfile" href={file.url} target="_blank" rel="noreferrer">
    <span className="dmfic">{fext(file.name)}</span>
    <span className="dmfname"><b>{file.name}</b><span className="small">{fsize(file.size)} · открыть</span></span></a>
}

// send(text, file, uid): file — {name, data, img} или null; uid один на отправку, повтор не создаёт второе сообщение.
// files={false} — только текст (объявление уходит и в бот).
function Composer({ send, ph, files = true }) {
  const [v, set] = useState('')
  const [att, setAtt] = useState(null)
  const [uid, setUid] = useState(uuid)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const inp = useRef(null)
  const pick = async f => {
    if (!f) return
    setErr('')
    const img = /^image\/(jpeg|png|webp|heic|heif)$/.test(f.type)
    try {
      if (img) { const data = await shrink(f).catch(() => null); if (data) return setAtt({ name: f.name.replace(/\.[^.]+$/, '') + '.jpg', data, img: true, size: Math.round(data.length * 0.75) }) }
      if (f.size > MAX_FILE) return setErr('Файл больше 20 МБ. Большое видео или макет положи в папку проекта и пришли ссылку.')
      setAtt({ name: f.name, data: await readUrl(f), size: f.size })
    } catch (e) { setErr(e.message || 'Файл не прочитался') }
  }
  const go = () => {
    if (!v.trim() && !att) return
    setBusy(true); setErr('')
    send(v.trim(), att, uid).then(() => { set(''); setAtt(null); setUid(uuid()) }, e => setErr(e.message)).finally(() => setBusy(false))
  }
  return <div className="dmform">
    <textarea rows={3} placeholder={ph} value={v} onChange={e => set(e.target.value)} />
    {att && <div className="dmatt">{att.img ? <img src={att.data} alt="" /> : <span className="dmfic">{fext(att.name)}</span>}
      <span className="dmfname"><b>{att.name}</b><span className="small muted">{fsize(att.size)}</span></span>
      <button className="ghost mini" aria-label="Убрать файл" onClick={() => setAtt(null)}>✕</button></div>}
    <div className="dmsend">
      {files && <><input ref={inp} type="file" hidden onChange={e => { pick(e.target.files[0]); e.target.value = '' }} />
        <button className="ghost dmclip" disabled={busy} onClick={() => inp.current?.click()}>📎 Файл или фото</button></>}
      <button disabled={busy || (!v.trim() && !att)} onClick={go}>{busy ? 'Отправляю…' : 'Отправить'}</button>
    </div>
    {err && <p className="small why">{err}</p>}
  </div>
}
const body = (text, att, uid) => ({ text, client_uid: uid, file: att ? { name: att.name, data: att.data } : null })

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
  if (open?.proj) return <ProjChat id={open.proj} back={back} />
  if (open) return <Pm who={open} back={back} />
  if (!d) return <div className="card muted">Загрузка…</div>
  if (d.err) return <div className="card muted">{d.err}</div>
  // HEAD 14.11: как в Telegram — где пришло новое или идёт переписка, тот чат наверху; чат проекта поднимается,
  // только когда в нём пишут (пустые чаты проектов — ниже, отдельным блоком).
  const ql = q.trim().toLowerCase()
  const hit = (...t) => !ql || t.some(v => (v || '').toLowerCase().includes(ql))
  const hqRow = { key: 'hq', at: d.hq.last_at, unread: +d.hq.unread || 0, el: <div key="hq" className="qrow dmrow dmhq" onClick={() => setOpen('hq')}>
    <span className="ic dmav hq">HEAD</span>
    <div className="qmain"><b>HEAD</b>{cnt(d.hq.unread)}
      <div className="small muted">{head ? 'вопросы команды и объявления · видят все HEAD' : 'объявления и вопросы руководству'}{d.hq.last_at ? ' · ' + when(d.hq.last_at) : ''}</div>
      {d.hq.last_text && <div className={'small dmlast' + (+d.hq.unread ? ' new' : '')}>{d.hq.last_text}</div>}
    </div><span className="muted">›</span></div> }
  const projRow = x => ({ key: 'p' + x.id, at: x.last_at, unread: +x.unread || 0, el: <div key={'p' + x.id} className="qrow dmrow dmproj" onClick={() => setOpen({ proj: x.id })}>
    <span className="ic dmav proj">№</span>
    <div className="qmain"><b>{cleanName(x.title, x.id)}</b>{cnt(x.unread)}
      <div className="small muted">Чат проекта · № {x.id}{x.open ? '' : ' · только чтение'}{x.last_at ? ' · ' + when(x.last_at) : ''}</div>
      {x.last_at && <div className={'small dmlast' + (+x.unread ? ' new' : '')}>{x.last_name?.split(' ')[0]}: {x.last_text || '📷 фото'}</div>}
    </div><span className="muted">›</span></div> })
  const pmRow = x => ({ key: 'u' + x.id, at: x.last_at, unread: +x.unread || 0, el: <div key={'u' + x.id} className="qrow dmrow" onClick={() => setOpen(x)}>
    <span className={'ic dmav' + (x.role_code === 'head' ? ' head' : '')}>{initials(x.full_name)}</span>
    <div className="qmain"><b>{x.full_name}</b>{cnt(x.unread)}
      <div className="small muted">{x.role_title}{x.last_at ? ' · ' + when(x.last_at) : ''}</div>
      {x.last_text && <div className={'small dmlast' + (+x.unread ? ' new' : '')}>{x.last_mine ? 'Вы: ' : ''}{x.last_text}</div>}
    </div><span className="muted">›</span></div> })
  const projs = (d.projects || []).filter(x => hit(x.title, String(x.id)))
  const people = d.people.filter(x => hit(x.full_name, x.role_title))
  const live = [...(hit('HEAD', 'руководство') ? [hqRow] : []), ...projs.filter(x => x.last_at || +x.unread).map(projRow),
    ...people.filter(x => x.last_at || +x.unread).map(pmRow)]
    .sort((a, b) => (b.unread > 0) - (a.unread > 0) || (b.at ? new Date(b.at) : 0) - (a.at ? new Date(a.at) : 0))
  const quiet = projs.filter(x => !x.last_at && !+x.unread && x.open), rest = people.filter(x => !x.last_at && !+x.unread)
  return <>
    <div className="card dm">
      <h2>Чат</h2>
      <input className="dmsearch" placeholder="Найти чат, человека или проект" value={q} onChange={e => setQ(e.target.value)} />
      {live.map(x => x.el)}
      {!live.length && !quiet.length && !rest.length && <p className="small muted">Ничего не нашлось.</p>}
    </div>
    {quiet.length > 0 && <div className="card dm">
      <h3>Чаты проектов</h3>
      <p className="small muted dmsub">Здесь ещё не писали. Как только напишут — чат поднимется наверх. Видят: кто на объекте, ГИП, МОП и HEAD.</p>
      {quiet.map(x => projRow(x).el)}
    </div>}
    {rest.length > 0 && <div className="card dm">
      <h3>Написать</h3>
      {rest.map(x => pmRow(x).el)}
      <p className="small muted dmsub">Личный чат видите только вы двое.</p>
    </div>}
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
    <Composer ph="Написать руководству" send={(t, f, u) => api('/dm/room/hq', { method: 'POST', body: body(t, f, u) }).then(load)} />
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
        <Composer ph={`Написать: ${who.full_name}`} send={(t, f, u) => api(`/dm/pm/${who.id}`, { method: 'POST', body: body(t, f, u) }).then(load)} /></> :
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
          <div className="small muted">{when(b.created_at)} · {b.author} · {b.roles?.length ? b.roles.map(r => d.roles.find(x => x.code === r)?.title || r).join(', ') : 'всем'} · получили {b.sent} · в боте {b.in_bot}</div>
          <Msg text={b.text} /></div>)}
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
          send={(t, f, u) => api(`/dm/with/${pid}`, { method: 'POST', body: body(t, f, u) }).then(load)} /></> :
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
      <Composer files={false} ph="Текст объявления"
        send={text => api('/dm/broadcast', { method: 'POST', body: { text, roles: pick.length ? pick : null } }).then(r => setOk(`Отправлено: ${r.sent} чел.`))} />}
  </div>
}

// чат проекта (HEAD 13.11): создаётся сам у проекта на «Выполнении»; видят кто на объекте, ГИП, МОП и все HEAD
const cleanName = (t, id) => (t || '').replace(new RegExp('^' + id + '\\s*·\\s*'), '')
const WHY = { gip: 'ГИП', mop: 'МОП', head: 'HEAD', crew: '' }
export function ProjChat({ id, back, backText = '‹ Все чаты' }) {
  const [d, setD] = useState(null)
  const [who, setWho] = useState(false)
  const load = () => api(`/pchat/${id}`).then(r => { setD(r); done() }, e => setD({ err: e.message }))
  useEffect(() => { load() }, [id])
  // фото — в папку сделки (МЕДИА / Отчёты), как раньше; другой файл — вложением чата
  const send = (t, f, u) => api(`/pchat/${id}`, { method: 'POST', body: f?.img ? { text: t, photo: f.data, client_uid: u } : body(t, f, u) }).then(load)
  if (!d) return <div className="card dm"><button className="ghost mini dmback" onClick={back}>{backText}</button><p className="small muted">Загрузка…</p></div>
  if (d.err) return <div className="card dm"><button className="ghost mini dmback" onClick={back}>{backText}</button><p className="small muted">{d.err}</p></div>
  const o = d.object
  return <div className="card dm">
    <button className="ghost mini dmback" onClick={back}>{backText}</button>
    <h2>Чат проекта</h2>
    <p className="small muted">№ {o.id} · {cleanName(o.title, o.id)}</p>
    <button className="ghost mini dmwhobtn" onClick={() => setWho(!who)}>Участники: {d.members.length} {who ? '▴' : '▾'}</button>
    {who && <div className="who dmmembers">{d.members.map(m => <span key={m.id}>{m.full_name}{WHY[m.why] ? ' · ' + WHY[m.why] : ''}</span>)}</div>}
    {d.items.length ? <div className="dmlist">
      {d.items.map(m => <div key={m.id} className={'dmb ' + (m.mine ? 'me' : 'them')}>
        {m.photo && <a href={m.photo.url} target="_blank" rel="noreferrer"><img loading="lazy" className="dmpic" src={m.photo.thumb} alt="" /></a>}
        <Att file={m.file} />
        {m.text && <Msg text={m.text} />}
        <span className="dmmeta">{m.mine ? '' : m.name + (m.head ? ' · HEAD' : '') + ' · '}{when(m.created_at)}</span>
      </div>)}
    </div> : <p className="small muted dmempty">Сообщений пока нет. Напиши первым — увидит вся команда проекта.</p>}
    {o.open ? <>
      <Composer ph="Написать команде проекта" send={send} />
      <p className="small dmwho">Фото ложится в папку сделки. Бот о чате не пишет — новое видно на вкладке «Чат».</p>
    </> : <p className="small muted">Проект ушёл с «Выполнения» — чат только для чтения.</p>}
  </div>
}

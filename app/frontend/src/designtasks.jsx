import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Sheet } from './ui.jsx'
import { cleanTitle, loadToday } from './crm.jsx'
import { Gallery, Viewer, uploadBig } from './objects.jsx'
import { CamLabel } from './camera.jsx'

// Задачи на дизайн при сделке (HEAD 25.11 «в целом норм, давай попробуем»): МОП жмёт «Нужен дизайн» в карточке сделки —
// сделка остаётся на своей стадии, у дизайнера карточка во вкладке «Дизайн» с его привычными стадиями.
// Единиц задачи не дают: единица одна за весь проект. Переписка с клиентом — в Битриксе, кнопкой из задачи.
const openUrl = u => { const t = window.Telegram?.WebApp; if (t?.openLink && t.initData) t.openLink(u); else window.open(u, '_blank', 'noopener') }
const dm = s => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}` : ''
const today = () => new Date().toISOString().slice(0, 10)
const tone = st => st === 'done' ? ' okt' : st === 'urgent' ? ' hott' : st === 'new' ? ' none' : ''
const who = t => [t.designer || 'дизайнер не назначен', t.deadline ? 'эскиз к ' + dm(t.deadline) : '', t.start_on ? 'старт ' + dm(t.start_on) : ''].filter(Boolean).join(' · ')
const left = s => s ? Math.round((new Date(s) - new Date(today())) / 864e5) : null
const days = n => `${n} ${n % 10 === 1 && n % 100 !== 11 ? 'день' : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? 'дня' : 'дней'}`
// Срок на карточке (HEAD 26.11): «осталось 2 дня», просроченное горит; на паузе «жду клиента» срок не горит.
function dueOf(t) {
  if (t.stage === 'done') return null
  if (t.stage === 'wait') return { text: 'пауза', cls: ' wait' }
  const n = left(t.deadline)
  if (n == null) return null
  return n < 0 ? { text: n === -1 ? 'срок вчера' : `просрочено ${days(-n)}`, cls: ' late' } : n === 0 ? { text: 'сегодня', cls: ' late' }
    : n === 1 ? { text: 'завтра', cls: ' soon' } : { text: days(n), cls: n <= 2 ? ' soon' : '' }
}
const burns = t => t.stage !== 'done' && t.stage !== 'wait' && (t.stage === 'urgent' || (left(t.deadline) != null && left(t.deadline) <= 1) || t.rounds >= 2)
// Лёгкий бриф (HEAD 26.11): МОП отвечает нажатиями. Те же варианты проверяет сервер (designtasks.BRIEF).
const BRIEF = [['who', 'Для кого', ['Дети', 'Взрослые', 'Сотрудники', 'Гости']],
  ['style', 'Стиль', ['Графика', 'Реализм', 'Минимализм', 'Абстракция', 'Граффити', 'Каллиграфия']],
  ['mood', 'Настроение', ['Энергия', 'Уют', 'Премиум', 'Детское', 'Спокойное']]]
// Ответы клиента из брифа по ссылке: подписи для дизайнера и МОП
const CLIENT = [['place', 'Объект'], ['where', 'Стена'], ['size', 'Размер'], ['who', 'Для кого'], ['style', 'Стиль'], ['mood', 'Настроение'], ['colors', 'Цвета'],
  ['idea', 'Идея'], ['must', 'Обязательно'], ['avoid', 'Не надо'], ['name', 'Утверждает'], ['phone', 'Телефон']]
const filled = cb => CLIENT.filter(([k]) => cb?.[k]).length

function BriefChips({ value, onChange }) {
  const flip = (k, o) => { const cur = value[k] || []; onChange({ ...value, [k]: cur.includes(o) ? cur.filter(x => x !== o) : [...cur, o] }) }
  return <>{BRIEF.map(([k, name, opts]) => <div key={k} className="dtq"><span className="small muted">{name}</span>
    <div className="chips sub">{opts.map(o => <button key={o} type="button" className={(value[k] || []).includes(o) ? 'on' : ''} onClick={() => flip(k, o)}>{o}</button>)}</div></div>)}</>
}
const briefTags = b => BRIEF.flatMap(([k]) => b?.[k] || [])

// Материалы к ТЗ (HEAD 26.11): фото стен, развёртки, примеры, логотип — пачкой. Ложатся в папку сделки «ДИЗАЙН / Фото объекта».
export function Materials({ dealId, canAdd, onCount }) {
  const [list, setList] = useState(null)
  const [busy, setBusy] = useState('')
  const [open, setOpen] = useState(null)
  const [all, setAll] = useState(false)
  const load = () => api(`/objects/${dealId}/files?kind=brief`).then(x => { setList(x); onCount?.(x.length) }, () => setList([]))
  useEffect(() => { api(`/design/deal/${dealId}/object`, { method: 'POST' }).then(load, () => setList([])) }, [dealId])
  const add = async files => {
    let bad = ''
    for (const [i, f] of [...files].entries()) {
      setBusy(`Загружаю ${i + 1} из ${files.length}: ${f.name}`)
      try { await uploadBig(dealId, 'brief', f, p => setBusy(`Загружаю ${i + 1} из ${files.length}: ${Math.round(p * 100)}%`)) } catch (e) { bad = `Не загрузилось «${f.name}»: ${e.message}` }
    }
    setBusy(bad); load()
  }
  const rows = list || []
  return <div className="dtmat">
    {canAdd && <div className="seg snapbtns"><CamLabel multi className="btnlike" onFiles={add}>📷 Снять</CamLabel>
      <label className="btnlike ghost">📎 Файлы пачкой
        <input type="file" multiple hidden onChange={e => { const f = [...e.target.files]; e.target.value = ''; f.length && add(f) }} /></label></div>}
    {busy && <p className="small muted">{busy}</p>}
    {!!rows.length && <div className="dtstrip">{(all ? rows : rows.slice(0, 4)).map(f => <button key={f.id} type="button" className="dtthumb" title={f.name} onClick={() => setOpen(f)}>
      {f.thumb ? <img src={f.thumb} alt="" loading="lazy" onError={e => { e.target.style.visibility = 'hidden' }} /> : <span>{(f.name.split('.').pop() || 'файл').slice(0, 4).toUpperCase()}</span>}</button>)}
      {!all && rows.length > 4 && <button type="button" className="dtthumb more" onClick={() => setAll(true)}>+{rows.length - 4}</button>}</div>}
    {list && !rows.length && !canAdd && <p className="small muted">Материалов пока нет.</p>}
    <Viewer f={open} onClose={() => setOpen(null)} list={rows.length > 1 ? rows : null} onNav={setOpen} />
  </div>
}

// Бриф клиенту ссылкой (HEAD 26.11): отправляют и МОП, и дизайнер — ссылка одна, ответы ложатся в эту же задачу.
export function BriefLink({ task, onClose }) {
  const [url, setUrl] = useState('')
  const [msg, setMsg] = useState('')
  useEffect(() => { api(`/design/tasks/${task.id}/brief-link`, { method: 'POST' }).then(r => setUrl(r.url), e => setMsg(e.message)) }, [task.id])
  const text = `Здравствуйте! Чтобы дизайнер ARTGAME точнее попал в ваш запрос, ответьте, пожалуйста, на 6 коротких вопросов — это 2 минуты, просто нажимайте варианты: ${url}`
  const copy = () => navigator.clipboard?.writeText(text).then(() => setMsg('Скопировано — вставьте клиенту в переписку.'), () => setMsg('Не скопировалось — выделите текст и скопируйте вручную.'))
  return <Sheet title="Бриф клиенту" onClose={onClose}>
    <p className="small muted">Клиент открывает ссылку без входа, на русском или казахском, и отвечает нажатиями. Ответы и фото стены сами попадут в задачу «{task.title}».</p>
    {url ? <><div className="dtlink">{text}</div>
      <button onClick={copy}>Скопировать сообщение</button>
      {navigator.share && <button className="ghost" onClick={() => navigator.share({ text }).catch(() => {})}>Поделиться…</button>}</> : !msg && <p className="muted small">Готовлю ссылку…</p>}
    {msg && <p className="small why">{msg}</p>}
  </Sheet>
}

// Что ответил клиент в брифе по ссылке
export function ClientBrief({ t }) {
  const cb = t.client_brief
  if (!cb) return t.brief_sent ? <p className="small muted">Бриф клиенту отправлен — ответа пока нет.</p> : null
  return <div className="dtbox"><p className="dtcap">Бриф клиента · {dm(t.client_brief_at)}{cb.lang === 'kk' ? ' · қаз' : ''}</p>
    {CLIENT.filter(([k]) => cb[k]).map(([k, name]) => <div key={k} className="dtkv"><span className="muted">{name}</span><b>{Array.isArray(cb[k]) ? cb[k].join(', ') : cb[k]}</b></div>)}</div>
}

// Вопросы дизайнера и ответы МОП по задаче
function Msgs({ t }) {
  if (!t.msgs?.length) return null
  return <div className="dtmsgs">{t.msgs.map(m => <div key={m.id} className={'dtmsg ' + m.kind}><span className="small muted">{m.by} · {dm(m.at)}</span><p>{m.text}</p></div>)}</div>
}



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
  const [all, setAll] = useState(false)
  useEffect(() => { api(`/objects/${dealId}/files?kind=design`).then(setList, () => setList([])) }, [dealId])
  if (!list.length) return null
  return <><p className="dtcap dtfiles">Эскизы · {list.length}</p>
    {(all ? list : list.slice(0, 3)).map(f => <div key={f.id} className="dtrow click" onClick={() => setOpen(f)}>
      {f.thumb ? <img className="dtthumb" src={f.thumb} alt="" /> : <span className="dtthumb">📄</span>}
      <div className="dtmain"><b>{f.name}</b><span className="small muted">{f.by} · {new Date(f.created_at).toLocaleDateString('ru-RU')}</span></div>
    </div>)}
    {list.length > 3 && <button className="ghost mini" onClick={() => setAll(!all)}>{all ? 'Свернуть ▴' : `Показать все ${list.length} ▾`}</button>}
    <Viewer f={open} onClose={() => setOpen(null)} /></>
}

// Окно «Нужен дизайн» (HEAD 26.11): ОДИН экран — что делаем, срок, материалы пачкой, лёгкий бриф кнопками и текст.
// Обязательны только название и срок эскиза; что МОП не знает — пропускает.
function NeedSheet({ dealId, onClose, onDone }) {
  const [v, setV] = useState({ title: '', deadline: '', start_on: '', urgent: false, brief: {}, note: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const ready = v.title.trim().length >= 2 && !!v.deadline
  const send = link => { setErr(''); setBusy(true)
    api(`/bx/deals/${dealId}/design-tasks`, { method: 'POST', body: { title: v.title.trim(), note: v.note.trim() || null, urgent: v.urgent,
      deadline: v.deadline, start_on: v.start_on || null, brief: v.brief } })
      .then(t => onDone(link ? t : null), e => { setErr(e.message); setBusy(false) }) }
  return <Sheet title="Нужен дизайн" onClose={onClose}>
    <label>Что делаем</label>
    <input value={v.title} maxLength={120} placeholder="Например: школа, коридоры и столовая" onChange={e => setV({ ...v, title: e.target.value })} />
    <div className="dttwo"><div><label>Эскиз к</label><input type="date" min={today()} value={v.deadline} onChange={e => setV({ ...v, deadline: e.target.value })} /></div>
      <div><label>Старт работ</label><input type="date" min={today()} value={v.start_on} onChange={e => setV({ ...v, start_on: e.target.value })} /></div></div>
    <label className="dtcheck"><input type="checkbox" checked={v.urgent} onChange={e => setV({ ...v, urgent: e.target.checked })} /> Срочно</label>
    <h3 className="dth">Материалы</h3>
    <p className="small muted">Фото стен, развёртки, примеры, логотип — сколько угодно сразу. Лягут в папку сделки.</p>
    <Materials dealId={dealId} canAdd />
    <h3 className="dth">Лёгкий бриф · что знаешь</h3>
    <BriefChips value={v.brief} onChange={brief => setV({ ...v, brief })} />
    <label>Задача дизайнеру</label>
    <textarea rows={3} value={v.note} maxLength={2000} placeholder="Размеры стен, тема, пожелания клиента, чего не надо" onChange={e => setV({ ...v, note: e.target.value })} />
    {err && <p className="small why">{err}</p>}
    {!ready && <p className="small muted">Нужны название и срок эскиза — остальное по желанию.</p>}
    <button className="ghost" disabled={!ready || busy} onClick={() => send(true)}>🔗 Отправить и дать клиенту бриф ссылкой</button>
    <button disabled={!ready || busy} onClick={() => send(false)}>Отправить дизайнеру</button>
  </Sheet>
}

// Блок «Дизайн» в карточке сделки (МОП и HEAD): задачи, срок, вопросы дизайнера, бриф клиента. МОП ничего не утверждает.
export function DealDesign({ dealId }) {
  const [d, setD] = useState(null)
  const [add, setAdd] = useState(false)
  const [link, setLink] = useState(null)
  const [ans, setAns] = useState({})
  const [err, setErr] = useState('')
  const load = () => api(`/bx/deals/${dealId}/design-tasks`).then(setD, () => setD({ items: [], can_add: false, off: true }))
  useEffect(() => { load() }, [dealId])
  if (!d || d.off || (!d.can_add && !d.items.length)) return null
  const drop = t => api(`/design/tasks/${t.id}/cancel`, { method: 'POST' }).then(load, e => setErr(e.message))
  const reply = t => { setErr(''); api(`/bx/deals/${dealId}/design-tasks/${t.id}/answer`, { method: 'POST', body: { text: (ans[t.id] || '').trim() } })
    .then(() => { setAns({ ...ans, [t.id]: '' }); load(); loadToday(true).catch(() => {}) }, e => setErr(e.message)) }
  return <div className="card dtdeal">
    <div className="head"><h3>Дизайн</h3>{!!d.items.length && <span className="badge">{d.items.length}</span>}</div>
    {d.items.map(t => { const due = dueOf(t); const q = t.ask_open && t.msgs[t.msgs.length - 1]
      return <div key={t.id} className="dttask">
        <div className="dtrow">
          <div className="dtmain"><b>{t.title}</b><span className="small muted">{who(t)}</span></div>
          {due && due.cls && <span className={'due' + due.cls}>{due.text}</span>}
          <span className={'tag' + tone(t.stage)}>{t.stage_name}</span>
          {d.can_add && t.stage === 'new' && <button className="pencil" aria-label="Убрать задачу" onClick={() => drop(t)}>✕</button>}
        </div>
        {(t.client_brief || t.sketches > 0) && <p className="small muted dtsub">{[t.client_brief ? `клиент заполнил бриф ${dm(t.client_brief_at)} · ${filled(t.client_brief)} ответов` : '',
          t.sketches ? `эскизы: утверждено ${t.sketches_ok} из ${t.sketches}` : ''].filter(Boolean).join(' · ')}</p>}
        {q && <div className="dtask"><p className="dtcap">Вопрос от дизайнера · {q.by}</p><p>«{q.text}»</p>
          {d.can_add && <><textarea rows={2} maxLength={1000} placeholder="Ответ дизайнеру" value={ans[t.id] || ''} onChange={e => setAns({ ...ans, [t.id]: e.target.value })} />
            <button className="mini" disabled={(ans[t.id] || '').trim().length < 2} onClick={() => reply(t)}>Ответить</button></>}</div>}
        {d.can_add && t.stage !== 'done' && !t.client_brief && <button className="ghost mini dtbl" onClick={() => setLink(t)}>🔗 {t.brief_sent ? 'Ссылка на бриф клиенту' : 'Бриф клиенту ссылкой'}</button>}
      </div> })}
    {!d.items.length && <p className="small muted">Задач на дизайн по этой сделке пока нет.</p>}
    <SeeFiles dealId={dealId} />
    {d.can_add && <button onClick={() => setAdd(true)}>+ Нужен дизайн</button>}
    {d.can_add && <p className="small muted">Сделка остаётся на своей стадии. Эскизы утверждает дизайнер у себя — здесь видны срок, статус и вопросы.</p>}
    {err && <p className="small why">{err}</p>}
    {add && <NeedSheet dealId={dealId} onClose={() => { setAdd(false); load() }} onDone={t => { setAdd(false); load(); t && setLink(t) }} />}
    {link && <BriefLink task={link} onClose={() => { setLink(null); load() }} />}
  </div>
}

// Сколько открытых задач у дизайнера — чтобы «Дизайн» сразу открывал доску, когда на ней что-то есть.
export function useTaskCount() {
  const [n, setN] = useState(null)
  useEffect(() => { api('/design/tasks').then(d => setN(d.items.filter(t => t.stage !== 'done').length), () => setN(0)) }, [])
  return n
}

const fresh = s => s && (Date.now() - new Date(s)) < 3 * 864e5
// «Ответили»: МОП ответил на вопрос или клиент заполнил бриф за последние три дня
const answered = t => t.stage !== 'done' && ((t.msgs?.length && t.msgs[t.msgs.length - 1].kind === 'answer' && fresh(t.msgs[t.msgs.length - 1].at)) || fresh(t.client_brief_at))

// Место дизайнера (HEAD 26.11): сверху «Сегодня» — что горит, кого ждём, новые, единицы месяца; ниже доска со сроками.
// Дизайнер видит свои и неразобранные, Главный и HEAD — все.
export function TaskBoard({ team, me }) {
  const [d, setD] = useState(null)
  const [u, setU] = useState(null)
  const [err, setErr] = useState('')
  const [only, setOnly] = useState('')
  const [open, setOpen] = useState(null)
  const load = () => api('/design/tasks').then(setD, e => setErr(e.message))
  useEffect(() => { load(); api('/design/units').then(setU, () => setU(null)) }, [])
  if (err) return <div className="card"><p className="small why">{err}</p></div>
  if (!d) return <div className="card"><p className="muted">Загружаю…</p></div>
  const live = d.items.filter(t => t.stage !== 'done')
  const mine = live.filter(t => t.designer_id === d.me), free = live.filter(t => !t.designer_id)
  const scope = only === 'mine' ? mine : only === 'free' ? free : only === 'wait' ? live.filter(t => t.stage === 'wait') : only === 'new' ? live.filter(t => t.stage === 'new' || t.stage === 'urgent') : d.items
  const order = ['urgent', 'work', 'fix', 'info', 'new', 'wait', 'mop', 'done']
  const name = Object.fromEntries(d.stages.map(s => [s.id, s.name]))
  const groups = order.map(k => [k, scope.filter(t => t.stage === k)]).filter(([, rows]) => rows.length)
  const hot = live.filter(burns), back = live.filter(answered)
  const waitN = live.filter(t => t.stage === 'wait').length, newN = live.filter(t => t.stage === 'new' || t.stage === 'urgent').length
  const Row = ({ t, k, tag }) => { const due = dueOf(t)
    return <div className="dtrow click" onClick={() => setOpen(t)}>
      <div className="dtmain"><b>№ {t.deal_id} {cleanTitle(t.deal_title, t.deal_id)} · {t.title}</b>
        <span className="small muted">{[t.city, t.size ? t.size.toUpperCase() : '', t.deadline ? 'эскиз к ' + dm(t.deadline) : 'без срока', t.rounds ? `правки, круг ${t.rounds}` : '',
          t.sketches ? `эскизы ${t.sketches_ok} из ${t.sketches}` : '', t.client_brief ? 'бриф клиента ✓' : '', t.materials ? `материалы ${t.materials}` : '',
          d.all ? (t.designer || 'не назначен') : (t.designer_id ? '' : 'свободна')].filter(Boolean).join(' · ')}</span></div>
      {tag ? <span className="tag none">{tag}</span> : t.ask_open ? <span className="due wait">ждём МОП</span> : due ? <span className={'due' + due.cls}>{due.text}</span> : k === 'new' ? <span className="tag none">взять</span> : null}
    </div> }
  return <>
    <div className="card dttoday">
      <div className="head"><h2>Сегодня{me?.full_name ? ', ' + me.full_name.split(' ')[0] : ''}</h2><button className="ghost mini" onClick={() => { setD(null); load() }}>Обновить</button></div>
      <div className="tiles">
        <button className={'dttile' + (hot.length ? ' hot' : '')} onClick={() => setOnly('')}><b>{hot.length}</b><span>горит срок</span></button>
        <button className={'dttile' + (only === 'wait' ? ' on' : '')} onClick={() => setOnly(only === 'wait' ? '' : 'wait')}><b>{waitN}</b><span>жду клиента</span></button>
        <button className={'dttile' + (only === 'new' ? ' on' : '')} onClick={() => setOnly(only === 'new' ? '' : 'new')}><b>{newN}</b><span>{newN === 1 ? 'новая' : 'новые'}</span></button>
      </div>
      {u && <p className="small muted dtunits">Месяц: <b>{String(u.mine || 0).replace('.', ',')}</b>{u.norm ? ` из ${String(u.norm).replace('.', ',')}` : ''} ед. · единица одна за проект, когда дизайн утверждён.</p>}
    </div>
    {!!hot.length && !only && <div className="card dtstage urgent dthot"><p className="dtcap">Горит · {hot.length}</p>{hot.map(t => <Row key={t.id} t={t} />)}</div>}
    {!!back.length && !only && <div className="card dtstage dtback"><p className="dtcap">Ответили · {back.length}</p>{back.map(t => <Row key={t.id} t={t} tag={fresh(t.client_brief_at) ? 'бриф клиента' : 'ответ МОП'} />)}</div>}
    <div className="chips scroll">
      <button className={!only ? 'on' : ''} onClick={() => setOnly('')}>Все <span>{live.length}</span></button>
      <button className={only === 'mine' ? 'on' : ''} onClick={() => setOnly(only === 'mine' ? '' : 'mine')}>Мои <span>{mine.length}</span></button>
      <button className={only === 'free' ? 'on' : ''} onClick={() => setOnly(only === 'free' ? '' : 'free')}>Свободные <span>{free.length}</span></button>
    </div>
    {groups.map(([k, rows]) => <div key={k} className={'card dtstage ' + k}>
      <p className="dtcap">{name[k]} · {rows.length}</p>
      {rows.map(t => <Row key={t.id} t={t} k={k} />)}
    </div>)}
    {!scope.length && <div className="card"><p className="small muted">{d.items.length ? 'Здесь пусто.' : 'Задач пока нет. Они появятся здесь, когда МОП нажмёт «Нужен дизайн» в карточке сделки.'}</p></div>}
    {open && <TaskSheet t={open} d={d} team={team} me={me} onClose={() => setOpen(null)} onDone={x => { setOpen(x || null); load() }} />}
  </>
}

// Карточка задачи (HEAD 26.11): сверху всё ТЗ в одном месте — от МОП, от клиента, материалы, вопросы; ниже эскизы и решение.
function TaskSheet({ t, d, team, me, onClose, onDone }) {
  const [err, setErr] = useState('')
  const [ask, setAsk] = useState(null)
  const [tz, setTz] = useState(null)
  const [link, setLink] = useState(false)
  const post = (path, body, close) => { setErr(''); return api(path, { method: 'POST', body }).then(x => { setAsk(null); setTz(null); onDone(close ? null : x) }, e => setErr(e.message)) }
  const save = (body, close) => post(`/design/tasks/${t.id}`, body, close)
  const mine = d.all || !t.designer_id || t.designer_id === d.me
  const designers = (team || []).filter(x => x.id)
  const due = dueOf(t), tags = briefTags(t.brief)
  return <Sheet title={`№ ${t.deal_id} · ${t.title}`} onClose={onClose}>
    <p className="small muted">{cleanTitle(t.deal_title, t.deal_id)}{t.city && !cleanTitle(t.deal_title, t.deal_id).includes(t.city) ? ' — ' + t.city : ''} · задача от {t.by}</p>
    <div className="dtmeta">{t.size && <span className="tag">{t.size.toUpperCase()}</span>}
      <span className={'tag' + (due?.cls === ' late' ? ' hott' : '')}>{t.deadline ? 'эскиз к ' + dm(t.deadline) : 'срок не указан'}{due && t.stage !== 'wait' && left(t.deadline) > 1 ? ` · осталось ${due.text}` : due ? ` · ${due.text}` : ''}</span>
      {t.start_on && <span className="tag">старт {dm(t.start_on)}</span>}
      {t.rounds > 0 && <span className={'tag' + (t.rounds >= 2 ? ' hott' : '')}>правки, круг {t.rounds}</span>}</div>

    <div className="dtbox"><p className="dtcap">ТЗ от МОП · {t.by}</p>
      {!!tags.length && <div className="dtmeta">{tags.map(x => <span key={x} className="tag">{x}</span>)}</div>}
      {t.note ? <p className="dtnote">{t.note}</p> : !tags.length && <p className="small muted">МОП ничего не написал — спросите кнопкой «Вопрос МОП».</p>}
      {t.tz_by && <p className="small muted">дополнил(а) {t.tz_by}</p>}</div>
    <ClientBrief t={t} />
    <p className="dtcap dtfiles">Материалы{t.materials ? ` · ${t.materials}` : ''}</p>
    <Materials dealId={t.deal_id} canAdd={mine} />
    <Msgs t={t} />
    {ask != null ? <div className="dtbox"><label>Вопрос МОП</label>
      <textarea rows={2} autoFocus maxLength={1000} placeholder="Например: логотип есть в векторе?" value={ask} onChange={e => setAsk(e.target.value)} />
      <p className="small muted">МОП увидит вопрос у себя в «Сегодня». Задача уйдёт в «Сбор информации» и вернётся, когда он ответит.</p>
      <div className="dttwo"><button className="ghost" onClick={() => setAsk(null)}>Отмена</button><button disabled={ask.trim().length < 2} onClick={() => post(`/design/tasks/${t.id}/ask`, { text: ask.trim() })}>Спросить</button></div></div>
      : tz != null ? <div className="dtbox"><label>Дополнить ТЗ</label>
        <BriefChips value={tz.brief} onChange={brief => setTz({ ...tz, brief })} />
        <textarea rows={4} maxLength={2000} value={tz.note} placeholder="Что выяснили из переписки с клиентом" onChange={e => setTz({ ...tz, note: e.target.value })} />
        <div className="dttwo"><button className="ghost" onClick={() => setTz(null)}>Отмена</button><button onClick={() => save({ note: tz.note, brief: tz.brief })}>Сохранить ТЗ</button></div></div>
        : <div className="dtbtns">
          {t.bitrix && <button className="ghost mini" onClick={() => openUrl(t.bitrix)}>Переписка</button>}
          {mine && t.stage !== 'done' && <button className="ghost mini" onClick={() => setAsk('')}>Вопрос МОП</button>}
          {mine && <button className="ghost mini" onClick={() => setTz({ note: t.note, brief: t.brief || {} })}>Дополнить ТЗ</button>}
          {mine && t.stage !== 'done' && !t.client_brief && <button className="ghost mini" onClick={() => setLink(true)}>Бриф клиенту</button>}
        </div>}

    <h3 className="dth">Эскизы{t.sketches ? ` · утверждено ${t.sketches_ok} из ${t.sketches}` : ''}</h3>
    <p className="small muted">Загрузите файл — он сам ляжет в папку сделки «ДИЗАЙН». «В работу» у файла — этот эскиз увидят МОП, ГИП и бригада.</p>
    <DealFiles dealId={t.deal_id} me={me} />
    <label>Стадия</label>
    <select value={t.stage} disabled={!mine} onChange={e => save({ stage: e.target.value })}>{d.stages.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
    {d.all ? <><label>Дизайнер</label>
      <select value={t.designer_id || ''} onChange={e => save({ designer_id: +e.target.value || null })}><option value="">не назначен</option>{designers.map(x => <option key={x.id} value={x.id}>{x.full_name}</option>)}</select></>
      : !t.designer_id && <button className="ghost" onClick={() => save({ designer_id: d.me, stage: t.stage === 'new' ? 'work' : t.stage })}>Беру в работу</button>}
    <div className="dttwo"><div><label>Размер</label>
      <select value={t.size} disabled={!mine} onChange={e => save({ size: e.target.value || null })}><option value="">—</option>{d.sizes.map(s => <option key={s} value={s}>{s.toUpperCase()}</option>)}</select></div>
      <div><label>Срок</label><input type="date" value={t.deadline} disabled={!mine} onChange={e => save({ deadline: e.target.value || null })} /></div></div>
    {err && <p className="small why">{err}</p>}
    {mine && t.stage !== 'done' && <div className="dttwo dtacts">
      {t.stage !== 'wait' ? <button className="ghost" onClick={() => save({ stage: 'wait' })}>Жду клиента</button> : <button className="ghost" onClick={() => save({ stage: 'work' })}>Клиент ответил</button>}
      {t.stage !== 'fix' ? <button className="ghost" onClick={() => save({ stage: 'fix' })}>Правки</button> : <span />}
    </div>}
    {mine && t.stage !== 'done' && <button className="okbtn" onClick={() => save({ stage: 'done' }, true)}>Утверждено</button>}
    <p className="small muted">«Жду клиента» ставит срок на паузу. После «Утверждено» МОП видит строку «передай в производство». Единица считается одна за весь проект.</p>
    {link && <BriefLink task={t} onClose={() => { setLink(false); onDone(t) }} />}
  </Sheet>
}

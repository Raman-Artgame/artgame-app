import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { CityPicker, WaitSheet, cityBase } from './ui.jsx'

// Общие куски блока МОП (HEAD 05.11): полоска месяца, связь с клиентом, итог звонка, лента, лиды, «Сегодня» очередью.
export const money = n => n ? Math.round(n).toLocaleString('ru-RU') + ' ₸' : '—'
const mln = n => n >= 1e6 ? (n / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 1 }) + ' млн' : Math.round(n / 1000) + ' тыс.'
export const dt = s => s ? new Date(s).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''
export const strip = s => (s || '').replace(/<[^>]+>/g, '').replace(/\[\/?[A-Za-z]+[^\]]*\]/g, '')
// Названия сделок из Битрикса часто капсом («КАФЕ — АСТАНА») — приводим к обычному регистру, аббревиатуры (ТОО, КП) не трогаем.
export const nice = t => /[а-яa-z]/.test(t || '') ? t : (t || '').toLowerCase().replace(/(^|[\s«(—-])(\S)/g, (m, a, b) => a + b.toUpperCase()).replace(/\b(тоо|ип|ао|кп|жк|тц|трц|бц|vip)\b/gi, w => w.toUpperCase())
export const cleanTitle = (title, id) => nice((title || '').replace(new RegExp(`^№?\\s*${id}\\s*·?\\s*`), ''))
export const ageDays = s => s ? Math.floor((Date.now() - new Date(s).getTime()) / 86400000) : 0
const tomorrow = () => new Date(Date.now() + 86400000).toISOString().slice(0, 10)

// Полоска месяца сверху: сколько закрыла компания и сколько до следующей ступени %. Один запрос на сеанс.
let monthCache = null
export function MonthStrip({ onOpen }) {
  const [m, setM] = useState(monthCache)
  useEffect(() => { if (!monthCache) api('/bx/month').then(r => { monthCache = r; setM(r) }, () => {}) }, [])
  if (!m) return null
  const co = m.company
  const steps = m.steps.filter(s => s.from)
  const target = co.next ? co.next.from : steps.length ? steps[steps.length - 1].from : 0
  const pct = target ? Math.min(100, Math.round(co.net / target * 100)) : 100
  return <div className="strip" onClick={onOpen}>
    <div className="strip-top"><span>Месяц: <b>{mln(co.net)}</b>{target ? <span className="muted"> из {mln(target)}</span> : null}</span>
      <span className="muted small">{co.step ? `${co.pct}%` : 'ступени нет'}{co.next ? ` · до ${steps[co.next.step - 1]?.pct}% ещё ${mln(co.next.left)}` : ''}</span></div>
    <div className="bar"><i style={{ width: pct + '%' }} /></div>
  </div>
}

// Связь с клиентом. Главная кнопка — карточка в Битриксе: там телефония и чат WhatsApp (Wazzup) с записью в сделку.
// Звонок и WhatsApp — только в карточке Битрикса (телефония и Wazzup там), решение HEAD 05.11.
let portalCache = null
export function usePortal() {
  const [p, setP] = useState(portalCache)
  useEffect(() => { if (portalCache === null) api('/bx/status').then(s => { portalCache = s.portal || ''; setP(portalCache); try { localStorage.setItem('artgame.bx.portal', portalCache) } catch { /* без памяти */ } }, () => setP('')) }, [])
  return p || ''
}
export const bxLink = (portal, entity, id) => portal ? `${portal}/crm/${entity}/details/${id}/` : ''
export function Contact({ phone, name, entity, id }) {
  const portal = usePortal()
  const link = bxLink(portal, entity, id)
  useEffect(() => { try { if (link) localStorage.setItem('artgame.bx.last', JSON.stringify({ entity, id, link, t: Date.now() })) } catch { /* без памяти */ } }, [link])
  return <div className="contact">
    <div><b>{name || '—'}</b><div className="small muted">{phone || 'телефона нет — добавьте в Битриксе'}</div></div>
    <div className="dealbtns">
      {link && <a className="btn ghost" href={link} target="_blank" rel="noreferrer">Позвонить · WhatsApp в Битриксе</a>}
    </div>
  </div>
}

const RESULTS = [['reached', 'Дозвонился'], ['no_answer', 'Не дозвонился'], ['callback', 'Перезвонить'], ['chat', 'Написал'], ['wait', 'Жду ответа']]
const inDays = n => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10)
// Итог звонка: в ленту Битрикса; «Перезвонить» — задача с датой и напоминание бота.
export function CallOutcome({ path, done, auto }) {
  const [f, setF] = useState(auto ? { result: 'reached', text: '', next: '' } : null)
  const [msg, setMsg] = useState('')
  const send = () => api(`${path}/call`, { method: 'POST', body: { result: f.result, text: f.text, next: f.next || null } })
    .then(r => { setF(null); setMsg(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Записано в Битрикс' + (r.task ? ', задача поставлена.' : '.')); done && done() },
      e => setMsg('Не записалось: ' + e.message))
  if (!f) return <>{msg && <p className="small muted">{msg}</p>}
    <button className="ghost" onClick={() => { setMsg(''); setF({ result: 'reached', text: '', next: '' }) }}>Итог звонка</button></>
  return <div className="dealedit">
    <div className="seg grid2">{RESULTS.map(([k, t]) => <button key={k} className={f.result === k ? '' : 'ghost'}
      onClick={() => setF({ ...f, result: k, next: k === 'callback' && !f.next ? tomorrow() : k === 'wait' && !f.next ? inDays(2) : f.next })}>{t}</button>)}</div>
    <input value={f.text} onChange={e => setF({ ...f, text: e.target.value })} placeholder="О чём договорились" />
    {f.result === 'wait' && <p className="small muted">До этой даты не горит — в этот день сам поднимется в «Сегодня».</p>}
    <label>{f.result === 'wait' ? 'Ждём до' : 'Перезвонить'}<input type="date" value={f.next} min={new Date().toISOString().slice(0, 10)} onChange={e => setF({ ...f, next: e.target.value })} /></label>
    <div className="dealbtns"><button disabled={f.result === 'wait' && !f.next} onClick={send}>Записать</button><button className="ghost" onClick={() => setF(null)}>Отмена</button></div>
  </div>
}

const KIND = { comment: ['💬', 'комментарий'], call: ['📞', 'звонок'], chat: ['🟢', 'чат'], email: ['✉️', 'письмо'],
  task: ['✅', 'задача'], meeting: ['🤝', 'встреча'], activity: ['•', 'дело'] }
export function Feed({ items }) {
  return <div className="card"><h3>История</h3>
    {!items.length && <p className="muted small">Пока пусто.</p>}
    {items.map((f, i) => { const [ic, name] = KIND[f.kind] || KIND.activity
      return <div key={i} className="feed"><span className="ic">{ic}</span><div>
        <div className="small muted">{name}{f.lead ? <span className="fromlead">из лида</span> : null}{f.dir === 'in' ? ' · входящий' : f.dir === 'out' ? ' · исходящий' : ''}{f.who ? ' · ' + f.who : ''} · {dt(f.at)}</div>
        <div>{strip(f.text).slice(0, 400) || '—'}</div></div></div> })}
  </div>
}

// ---------- «Сегодня»: очередь дня ----------
// Один запрос на сеанс: экран «Сегодня» и счётчики в меню читают один и тот же ответ.
let todayCache = null
let todayLoading = null   // экран и счётчики меню открываются вместе — один запрос на двоих
const todayWatchers = new Set()
export function loadToday(fresh) {
  if (todayLoading && !fresh) return todayLoading
  const p = api(`/bx/today${fresh ? '?fresh=1' : ''}`).then(r => { todayCache = r; todayWatchers.forEach(f => f(r)); return r })
    .finally(() => { if (todayLoading === p) todayLoading = null })
  todayLoading = p
  return p
}
export function useToday(enabled = true) {
  const [t, setT] = useState(todayCache)
  useEffect(() => {
    if (!enabled) return undefined
    todayWatchers.add(setT)
    if (!todayCache) loadToday(false).catch(() => {})
    return () => todayWatchers.delete(setT)
  }, [enabled])
  return enabled ? t : null
}

const BUCKETS = [['hot', 'Горит', 'Просрочено или ждёт ответа дольше нормы'], ['today', 'Сегодня', 'Сделать сегодня'], ['later', 'Можно позже', 'Без движения, задачи без срока']]
const KINDS = { lead: 'Лиды', deal: 'Сделки', task: 'Задачи' }
const initial = s => ((s || '?').trim()[0] || '?').toUpperCase()
const dayName = () => { const d = new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' }); return d[0].toUpperCase() + d.slice(1) }
export function Today({ openDeal, openLead, openMonth }) {
  const portal = usePortal()
  const t = useToday()
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [only, setOnly] = useState('')
  const [wait, setWait] = useState(null)
  const [note, setNote] = useState('')
  useEffect(() => { if (!t) loadToday(false).catch(e => setErr(e.message)) }, [])
  const reload = () => { setBusy(true); loadToday(true).catch(e => setErr(e.message)).finally(() => setBusy(false)) }
  if (err && !t) return <div className="card"><h2>Сегодня</h2><p className="muted">{err}</p></div>
  if (!t) return <Skeleton n={3} />
  const q = t.queue
  const open = x => x.entity === 'lead' ? openLead(x.id) : x.entity === 'deal' ? openDeal(x.id) : x.deal && openDeal(x.deal)
  const total = q.hot.length + q.today.length
  const row = x => <div key={x.entity + x.id} className={'qrow ' + x.entity}>
    <span className={'ic ' + x.entity}>{x.entity === 'lead' ? initial(x.name || x.title) : x.entity === 'deal' ? '№' : '✓'}</span>
    <div className="qmain" onClick={() => open(x)}>
      <div className="qt">{x.entity === 'task' ? x.title : x.entity === 'lead' ? <b>{x.name || x.title}</b> : <><b>№ {x.id}</b> {cleanTitle(x.title, x.id)}</>}</div>
      <div className="small why">{x.why}</div>
      {(x.stage || x.sum) ? <div className="small muted">{[x.stage, x.sum ? money(x.sum) : ''].filter(Boolean).join(' · ')}</div> : null}
    </div>
    <div className="qbtns">
      {(x.action === 'call' || x.action === 'chat') && x.entity !== 'task' && portal ? <a className="btn mini" href={bxLink(portal, x.entity, x.id)} target="_blank" rel="noreferrer">{x.action === 'chat' ? 'Ответить' : 'Позвонить'}</a>
        : <button className="ghost mini" onClick={() => open(x)}>Открыть</button>}
      {x.entity !== 'task' && !x.wait && <button className="ghost mini" onClick={() => setWait(x)}>Жду ответа</button>}
    </div>
  </div>
  return <>
    <div className="card">
      <div className="head"><div><h2>Сегодня</h2><div className="small muted">{dayName()}</div></div>
        <button className="ghost mini" disabled={busy} onClick={reload}>{busy ? '…' : 'Обновить'}</button></div>
      <div className="tiles">{BUCKETS.map(([k, title]) => <button key={k} className={'tile ' + k + (only === k ? ' on' : '')} onClick={() => setOnly(only === k ? '' : k)}><b>{q[k].length}</b><span>{title}</span></button>)}</div>
      {t.warn ? <p className="small" style={{ color: 'var(--hot)' }}>{t.warn}</p> : null}
      {note && <p className="small ok">{note}</p>}
      {!total && !q.later.length && <p className="small muted">Срочного нет. Хороший момент позвонить тем, кто давно молчит.</p>}
    </div>
    {BUCKETS.filter(([k]) => !only || only === k).map(([k, title, hint]) => {
      const items = q[k]
      const kinds = Object.keys(KINDS).filter(e => items.some(x => x.entity === e))
      if (!items.length && !only) return null   // пустые разделы не показываем — плитки сверху уже говорят «0»
      return <div key={k} className={'card bucket ' + k}>
        <h3>{title} <span className="muted small">{items.length}</span></h3>
        <p className="small muted">{items.length ? hint : k === 'hot' ? 'Ничего не горит.' : 'Пусто.'}</p>
        {kinds.map(e => <div key={e}>
          {kinds.length > 1 && <div className="subhead">{KINDS[e]} · {items.filter(x => x.entity === e).length}</div>}
          {items.filter(x => x.entity === e).map(row)}
        </div>)}
      </div>
    })}
    <MonthStrip onOpen={openMonth} />
    {wait && <WaitSheet api={api} path={`/bx/${wait.entity === 'lead' ? 'leads' : 'deals'}/${wait.id}`} title={`Жду ответа: ${wait.entity === 'lead' ? wait.name || wait.title : '№ ' + wait.id}`}
      onClose={() => setWait(null)} onDone={m => { setWait(null); setNote(m); setTimeout(() => setNote(''), 6000); reload() }} />}
  </>
}

// Серые заготовки вместо «Загружаю…»: экран не прыгает, когда придут данные.
export const Skeleton = ({ n = 3 }) => <div className="card skel">{Array.from({ length: n }, (_, i) => <div key={i} className="skrow"><i /><div><b /><span /></div></div>)}</div>

// ---------- Лиды ----------

export function Leads({ openLead }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [seg, setSeg] = useState(null)   // new | work | all
  const load = fresh => { setBusy(true); setErr(''); return api(`/bx/leads${fresh ? '?fresh=1' : ''}`).then(setD, e => setErr(e.message)).finally(() => setBusy(false)) }
  useEffect(() => { load(false) }, [])
  if (err) return <div className="card"><h2>Лиды</h2><p className="muted">{err}</p></div>
  if (!d) return <Skeleton n={4} />
  const hours = l => Math.max(0, Math.round((Date.now() - new Date(l.created)) / 3600000))
  // новые — кто дольше ждёт, тот выше; в работе — кто дольше без движения
  const news = d.leads.filter(l => l.new).sort((a, b) => hours(b) - hours(a)), work = d.leads.filter(l => !l.new).sort((a, b) => ageDays(b.modified) - ageDays(a.modified))
  const cur = seg || (news.length ? 'new' : 'work')
  const s = q.trim().toLowerCase()
  const base = s ? d.leads : cur === 'new' ? news : cur === 'work' ? work : d.leads
  const list = base.filter(l => !s || (l.name + ' ' + l.title + ' ' + l.phone + ' ' + (l.manager || '')).toLowerCase().includes(s))
  return <>
    <div className="card"><div className="head"><h2>{d.all ? 'Лиды' : 'Мои лиды'}</h2>
      <button className="ghost mini" disabled={busy} onClick={() => load(true)}>{busy ? '…' : 'Обновить'}</button></div>
      <div className="segf">
        <button className={cur === 'new' && !s ? 'on' : ''} onClick={() => setSeg('new')}>Новые <span>{news.length}</span></button>
        <button className={cur === 'work' && !s ? 'on' : ''} onClick={() => setSeg('work')}>В работе <span>{work.length}</span></button>
        <button className={cur === 'all' || s ? 'on' : ''} onClick={() => setSeg('all')}>Все <span>{d.leads.length}</span></button>
      </div>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Имя или телефон" />
      {!list.length && <p className="muted">{cur === 'new' && !s ? 'Новых лидов нет.' : 'Пусто.'}</p>}
      {list.map(l => <div key={l.id} className="qrow lead" onClick={() => openLead(l.id)}>
        <span className="ic lead">{initial(l.name)}</span>
        <div className="qmain"><div className="qt"><b>{l.name}</b></div>
          <div className="small muted">{[l.phone, l.city, l.manager].filter(Boolean).join(' · ')}</div>
          {!!l.missing.length && <div>{l.missing.map(m => <span key={m} className="miss">нет: {m}</span>)}</div>}</div>
        <span className={'badge' + ((l.new ? hours(l) >= (d.new_hours || 4) : ageDays(l.modified) >= 3) ? ' hot' : '')}>{l.new ? (hours(l) ? `ждёт ${hours(l)} ч` : 'только что') : `${ageDays(l.modified)} дн.`}</span>
      </div>)}
    </div>
  </>
}

export function LeadCard({ id, back, openDeal }) {
  const [l, setL] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [f, setF] = useState({ name: '', city: '', cityName: '', service: '', area: '', sum: '' })
  // HEAD 06.11 «пожестче», 07.11 «чтобы реально работало»: в сделку — одной кнопкой, без отдельного «Сохранить».
  // Обязательно: имя, телефон, город, услуга и объект (из объекта и города — название сделки). Площадь — перед КП.
  const convKey = `artgame.lead.conv.${id}`
  const blank = { service: '', area: '', address: '', object: '' }
  const [cv, setCv] = useState(() => { try { return { ...blank, ...(JSON.parse(localStorage.getItem(convKey)) || {}) } } catch { return blank } })
  const [dict, setDict] = useState({ services: [] })
  const [cities, setCities] = useState([])
  const [fail, setFail] = useState(null)
  const [vac, setVac] = useState(false)
  const [title, setTitle] = useState(null)   // правка названия лида
  const [wait, setWait] = useState(false)
  const [reasons, setReasons] = useState([])
  const load = fresh => api(`/bx/leads/${id}${fresh ? '?fresh=1' : ''}`).then(r => {
    setL(r); setF({ name: r.client_name || '', city: r.city_id, cityName: r.city, service: r.service_id, area: r.area || '', sum: r.sum || '' })
  }, e => setErr(e.message))
  useEffect(() => { load(false); api('/bx/leads/cities').then(setCities, () => {}); api('/bx/reasons').then(setReasons, () => {}); api('/bx/dict').then(setDict, () => {}) }, [id])
  if (err) return <div className="card"><a onClick={back}>← назад</a><p className="muted">{err}</p></div>
  if (!l) return <Skeleton n={2} />
  const setC = (k, v) => { const n = { ...cv, [k]: v }; setCv(n); try { localStorage.setItem(convKey, JSON.stringify(n)) } catch { /* без памяти */ } }
  const note = r => r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Записано в Битрикс.'
  const say = p => p.then(r => { setMsg(note(r)); return load(true) }, e => setMsg('Не записалось: ' + e.message))
  const saveBody = { name: f.name.trim() !== (l.client_name || '') ? f.name.trim() : null, city: f.city !== l.city_id ? f.city || null : null,
    service: f.service !== l.service_id ? f.service || null : null, area: (+f.area || 0) !== (l.area || 0) ? +f.area || null : null, sum: (+f.sum || 0) !== (l.sum || 0) ? +f.sum || null : null }
  const changed = Object.values(saveBody).some(v => v !== null && v !== '')
  const save = () => say(api(`/bx/leads/${id}`, { method: 'POST', body: saveBody }))
  const svc = l.has.service ? f.service : cv.service
  const miss = [!f.name.trim() && 'имя клиента', l.missing.includes('телефон') && 'телефон', !f.city && 'город', !svc && 'услуга', !cv.object.trim() && 'объект'].filter(Boolean)
  const req = m => miss.includes(m) ? 'need' : ''
  const preview = cv.object.trim() ? `№ · ${cv.object.trim().toUpperCase()}${f.cityName ? ' — ' + cityBase(f.cityName).toUpperCase() : ''}` : ''
  const convert = async () => {
    setBusy(true); setMsg('')
    try {
      if (changed) await api(`/bx/leads/${id}`, { method: 'POST', body: saveBody })
      const r = await api(`/bx/leads/${id}/convert`, { method: 'POST', body: { service: l.has.service ? null : cv.service || null,
        area: l.has.area ? null : +cv.area || null, address: cv.address.trim() || null, object: cv.object.trim() } })
      try { localStorage.removeItem(convKey) } catch { /* ок */ }
      openDeal(r.deal)
    } catch (e) { setMsg('Не получилось: ' + e.message); load(true) } finally { setBusy(false) }
  }
  const setStatus = (status, extra = {}) => say(api(`/bx/leads/${id}/status`, { method: 'POST', body: { status, ...extra } }))
  return <>
    <div className="card">
      <a onClick={back}>← к лидам</a>
      {title === null ? <h2>{l.name} <span className="muted small">лид</span></h2>
        : <div className="titleedit"><input value={title} onChange={e => setTitle(e.target.value)} placeholder="Название лида" autoFocus />
          <button className="mini" disabled={!title.trim() || title.trim() === (l.title || '')} onClick={() => say(api(`/bx/leads/${id}`, { method: 'POST', body: { title } })).then(() => setTitle(null))}>Записать</button>
          <button className="ghost mini" onClick={() => setTitle(null)}>Отмена</button></div>}
      <span className="tag">{l.status_name}</span>{l.manager && <span className="tag">{l.manager}</span>}
      {title === null && <p className="small muted">{l.title && l.title !== l.name ? l.title : 'Название'} <button className="pencil" aria-label="Изменить название" onClick={() => setTitle(l.title || '')}>✎</button></p>}
      <Contact phone={l.phone} name={l.name} entity="lead" id={l.id} />
      <CallOutcome path={`/bx/leads/${id}`} done={() => load(true)} />
      <button className="ghost" onClick={() => setWait(true)}>Жду ответа</button>
    </div>
    <Origin id={id} origin={l.origin} done={() => load(false)} />
    <div className="card"><h3>В сделку</h3>
      {miss.length ? <p className="small">Не хватает: {miss.map(m => <span key={m} className="miss">{m}</span>)}</p> : <p className="small ok">Всё есть — можно в сделку.</p>}
      <div className="fillgrid">
        <label className={req('объект')} style={{ gridColumn: '1 / -1' }}><span>Объект</span><input value={cv.object} onChange={e => setC('object', e.target.value)} placeholder="Что за место: «Школа №12», «Кофейня Daily», «Квартира ЖК Highvill»" /></label>
        <CityPicker cities={cities} value={f.city} need={!f.city} onPick={(cid, name) => setF({ ...f, city: cid, cityName: name })} />
        <label className={req('имя клиента')}><span>Имя клиента</span><input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Как обращаться" /></label>
        {l.has.service
          ? <label className={req('услуга')}><span>Услуга</span><select value={f.service} onChange={e => setF({ ...f, service: e.target.value })}>
            <option value="">—</option>{l.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          : <label className={req('услуга')}><span>Услуга</span><select value={cv.service} onChange={e => setC('service', e.target.value)}>
            <option value="">—</option>{dict.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}
        {l.has.area
          ? <label><span>Площадь, м² <i className="muted small">можно позже</i></span><input type="number" min="1" inputMode="decimal" value={f.area} onChange={e => setF({ ...f, area: e.target.value })} /></label>
          : <label><span>Площадь, м² <i className="muted small">можно позже</i></span><input type="number" min="1" inputMode="decimal" value={cv.area} onChange={e => setC('area', e.target.value)} /></label>}
        <label><span>Адрес объекта</span><input value={cv.address} onChange={e => setC('address', e.target.value)} placeholder="Улица, дом" /></label>
        <label><span>Бюджет, ₸</span><input type="number" min="0" value={f.sum} onChange={e => setF({ ...f, sum: e.target.value })} /></label>
      </div>
      {preview && <div className="titleprev">Название сделки: <b>{preview}</b></div>}
      {l.missing.includes('телефон') && <p className="small">Телефона нет — добавьте его в карточке лида в Битриксе (кнопка выше), потом обновите.</p>}
      <button disabled={!!miss.length || busy} onClick={convert}>{busy ? 'Создаю сделку…' : 'В сделку'}</button>
      {!!miss.length && <p className="small muted">🔒 Заполните: {miss.join(', ')}.</p>}
      {changed && <button className="ghost" disabled={busy} onClick={save}>Только сохранить в лид</button>}
      {msg && <p className="small muted">{msg}</p>}
    </div>
    <div className="card"><h3>Не клиент</h3>
      <div className="dealbtns wrapbtns">
        <button className={'ghost' + (fail ? ' on' : '')} onClick={() => { setVac(false); setFail(fail ? null : { status: l.fail[0]?.id || '', code: '', reason: '' }) }}>Отказ</button>
        {!!l.vacancy?.length && <button className={'ghost' + (vac ? ' on' : '')} onClick={() => { setFail(null); setVac(!vac) }}>Это вакансия</button>}
      </div>
      {vac && <div className="dealedit">
        <p className="small muted">Пишет соискатель, а не клиент. Причина не нужна, в очереди МОП лида больше не будет.</p>
        {l.vacancy.map(v => <button key={v.id} className={v.keep ? '' : 'ghost'} onClick={() => setStatus(v.id).then(() => setVac(false))}>
          {v.keep ? 'Сохранить контакт' : 'Убрать'} <span className="small muted">· {v.name}</span></button>)}
      </div>}
      {fail && <div className="dealedit">
        <select value={fail.status} onChange={e => setFail({ ...fail, status: e.target.value })}>{l.fail.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
        <p className="small muted">Причина — одна из списка (HEAD 06.11), к ней строка комментария.</p>
        <div className="chips">{reasons.map(r => <button key={r.code} className={fail.code === r.code ? 'on' : ''} onClick={() => setFail({ ...fail, code: r.code })}>{r.name}</button>)}</div>
        <input value={fail.reason} onChange={e => setFail({ ...fail, reason: e.target.value })} placeholder="Комментарий: что сказал клиент" />
        <div className="dealbtns"><button disabled={!fail.code} onClick={() => setStatus(fail.status, { reason: fail.reason, reason_code: fail.code }).then(() => setFail(null))}>Закрыть лид</button>
          <button className="ghost" onClick={() => setFail(null)}>Отмена</button></div></div>}
    </div>
    <Feed items={l.feed} />
    {wait && <WaitSheet api={api} path={`/bx/leads/${id}`} onClose={() => setWait(false)} onDone={t => { setWait(false); setMsg(t); load(true); loadToday(true).catch(() => {}) }} />}
  </>
}


// «Откуда клиент» (HEAD 14.11): площадка лида для «Маркетинг → Реклама». Сама — по ссылке площадки; иначе спрашивает и отмечает МОП.
function Origin({ id, origin, done }) {
  const [list, setList] = useState(null)
  const [open, setOpen] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api('/mkt/channels').then(setList, () => setList([])) }, [])
  if (!list || !list.length) return null
  const pick = c => api(`/bx/leads/${id}/origin`, { method: 'POST', body: { channel_id: c.id } }).then(() => { setOpen(false); done() }, e => setErr(e.message))
  return <div className="card origin"><h3>Откуда клиент</h3>
    {origin && !open ? <p><b>{origin.title}</b> <span className="small muted">{origin.auto ? '· определилось само по ссылке' : '· отмечено'}</span> <a onClick={() => setOpen(true)}>изменить</a></p>
      : <><p className="small muted">Спроси «Как вы о нас узнали?» и отметь. По этому видно, какая реклама приводит клиентов.</p>
        <div className="chips">{list.map(c => <button key={c.id} className={origin?.channel_id === c.id ? 'on' : ''} onClick={() => pick(c)}>{c.title}</button>)}</div></>}
    {err && <p className="small why">{err}</p>}
  </div>
}

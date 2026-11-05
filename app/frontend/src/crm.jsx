import React, { useEffect, useState } from 'react'
import { api } from './api.js'

// Общие куски блока МОП (HEAD 05.11): полоска месяца, связь с клиентом, итог звонка, лента, лиды, «Сегодня» очередью.
export const money = n => n ? Math.round(n).toLocaleString('ru-RU') + ' ₸' : '—'
const mln = n => n >= 1e6 ? (n / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 1 }) + ' млн' : Math.round(n / 1000) + ' тыс.'
export const dt = s => s ? new Date(s).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''
export const strip = s => (s || '').replace(/<[^>]+>/g, '').replace(/\[\/?[A-Za-z]+[^\]]*\]/g, '')
export const cleanTitle = (title, id) => (title || '').replace(new RegExp(`^№?\\s*${id}\\s*·?\\s*`), '')
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
    <div className="strip-top"><span>Месяц: <b>{mln(co.net)}</b>{target ? ` из ${mln(target)}` : ''}</span>
      <span className="muted">{co.step ? `${co.pct}%` : 'ступени нет'}</span></div>
    <div className="bar"><i style={{ width: pct + '%' }} /></div>
    {co.next && <div className="small muted">до {steps[co.next.step - 1]?.pct}% ещё {mln(co.next.left)} без НДС</div>}
  </div>
}

// Связь с клиентом. Главная кнопка — карточка в Битриксе: там телефония и чат WhatsApp (Wazzup) с записью в сделку.
// Звонок и WhatsApp — только в карточке Битрикса (телефония и Wazzup там), решение HEAD 05.11.
let portalCache = null
export function usePortal() {
  const [p, setP] = useState(portalCache)
  useEffect(() => { if (portalCache === null) api('/bx/status').then(s => { portalCache = s.portal || ''; setP(portalCache) }, () => setP('')) }, [])
  return p || ''
}
export const bxLink = (portal, entity, id) => portal ? `${portal}/crm/${entity}/details/${id}/` : ''
export function Contact({ phone, name, entity, id }) {
  const portal = usePortal()
  const link = bxLink(portal, entity, id)
  return <div className="contact">
    <div><b>{name || '—'}</b><div className="small muted">{phone || 'телефона нет — добавьте в Битриксе'}</div></div>
    <div className="dealbtns">
      {link && <a className="btn" href={link} target="_blank" rel="noreferrer">Позвонить · WhatsApp в Битриксе</a>}
    </div>
  </div>
}

const RESULTS = [['reached', 'Дозвонился'], ['no_answer', 'Не дозвонился'], ['callback', 'Перезвонить'], ['chat', 'Написал']]
// Итог звонка: в ленту Битрикса; «Перезвонить» — задача с датой и напоминание бота.
export function CallOutcome({ path, done }) {
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState('')
  const send = () => api(`${path}/call`, { method: 'POST', body: { result: f.result, text: f.text, next: f.next || null } })
    .then(r => { setF(null); setMsg(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Записано в Битрикс' + (r.task ? ', задача поставлена.' : '.')); done && done() },
      e => setMsg('Не записалось: ' + e.message))
  if (!f) return <>{msg && <p className="small muted">{msg}</p>}
    <button className="ghost" onClick={() => { setMsg(''); setF({ result: 'reached', text: '', next: '' }) }}>Итог звонка</button></>
  return <div className="dealedit">
    <div className="seg grid2">{RESULTS.map(([k, t]) => <button key={k} className={f.result === k ? '' : 'ghost'}
      onClick={() => setF({ ...f, result: k, next: k === 'callback' && !f.next ? tomorrow() : f.next })}>{t}</button>)}</div>
    <input value={f.text} onChange={e => setF({ ...f, text: e.target.value })} placeholder="О чём договорились" />
    <label>Перезвонить<input type="date" value={f.next} min={new Date().toISOString().slice(0, 10)} onChange={e => setF({ ...f, next: e.target.value })} /></label>
    <div className="dealbtns"><button onClick={send}>Записать</button><button className="ghost" onClick={() => setF(null)}>Отмена</button></div>
  </div>
}

const KIND = { comment: ['💬', 'комментарий'], call: ['📞', 'звонок'], chat: ['🟢', 'чат'], email: ['✉️', 'письмо'],
  task: ['✅', 'задача'], meeting: ['🤝', 'встреча'], activity: ['•', 'дело'] }
export function Feed({ items }) {
  return <div className="card"><h3>История</h3>
    {!items.length && <p className="muted small">Пока пусто.</p>}
    {items.map((f, i) => { const [ic, name] = KIND[f.kind] || KIND.activity
      return <div key={i} className="feed"><span className="ic">{ic}</span><div>
        <div className="small muted">{name}{f.dir === 'in' ? ' · входящий' : f.dir === 'out' ? ' · исходящий' : ''}{f.who ? ' · ' + f.who : ''} · {dt(f.at)}</div>
        <div>{strip(f.text).slice(0, 400) || '—'}</div></div></div> })}
  </div>
}

// ---------- «Сегодня»: одна очередь, три корзины ----------

const BUCKETS = [['hot', 'Горит', 'Просрочено или ждёт ответа дольше нормы'], ['today', 'Сегодня', 'Сделать сегодня'], ['later', 'Можно позже', 'Без движения, задачи без срока']]
export function Today({ openDeal, openLead, openMonth }) {
  const portal = usePortal()
  const [t, setT] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const load = fresh => { setBusy(true); return api(`/bx/today${fresh ? '?fresh=1' : ''}`).then(setT, e => setErr(e.message)).finally(() => setBusy(false)) }
  useEffect(() => { load(false) }, [])
  if (err) return <div className="card"><h2>Сегодня</h2><p className="muted">{err}</p></div>
  if (!t) return <div className="card muted">Смотрю, что срочно…</div>
  const q = t.queue
  const open = x => x.entity === 'lead' ? openLead(x.id) : x.entity === 'deal' ? openDeal(x.id) : x.deal && openDeal(x.deal)
  const total = q.hot.length + q.today.length
  return <>
    <MonthStrip onOpen={openMonth} />
    <div className="card"><div className="head"><h2>Сегодня</h2><button className="ghost mini" disabled={busy} onClick={() => load(true)}>{busy ? '…' : 'Обновить'}</button></div>
      <p className="muted">{total ? `Сделать: ${total}` : 'Срочного нет. Можно заняться тем, что «позже».'}</p></div>
    {BUCKETS.map(([k, title, hint]) => (k !== 'later' || q[k].length) ? <div key={k} className={'card bucket ' + k}>
      <h3>{title} <span className="muted small">{q[k].length}</span></h3>
      {!q[k].length && <p className="muted small">{k === 'hot' ? 'Ничего не горит.' : 'Пусто.'}</p>}
      {q[k].length > 0 && <p className="small muted">{hint}</p>}
      {q[k].map(x => <div key={x.entity + x.id} className="qrow">
        <div className="qmain" onClick={() => open(x)}>
          <div><span className="kind">{x.entity === 'lead' ? 'лид' : x.entity === 'deal' ? 'сделка' : 'задача'}</span>
            {x.entity === 'task' ? x.title : <><b>№ {x.id}</b> {x.entity === 'lead' ? (x.name || x.title) : cleanTitle(x.title, x.id)}</>}</div>
          <div className="small why">{x.why}{x.sum ? ' · ' + money(x.sum) : ''}</div>
        </div>
        {x.action === 'call' && x.entity !== 'task' && portal ? <a className="btn mini" href={bxLink(portal, x.entity, x.id)} target="_blank" rel="noreferrer">Позвонить</a>
          : <button className="ghost mini" onClick={() => open(x)}>Открыть</button>}
      </div>)}
    </div> : null)}
  </>
}

// ---------- Лиды ----------

export function Leads({ openLead, openMonth }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const load = fresh => { setBusy(true); return api(`/bx/leads${fresh ? '?fresh=1' : ''}`).then(setD, e => setErr(e.message)).finally(() => setBusy(false)) }
  useEffect(() => { load(false) }, [])
  if (err) return <div className="card"><h2>Лиды</h2><p className="muted">{err}</p></div>
  if (!d) return <div className="card muted">Загружаю лиды из Битрикса…</div>
  const s = q.trim().toLowerCase()
  const list = d.leads.filter(l => !s || String(l.id).includes(s) || (l.name + ' ' + l.title + ' ' + l.phone + ' ' + (l.manager || '')).toLowerCase().includes(s))
  const groups = [['Новые', list.filter(l => l.new)], ['В работе', list.filter(l => !l.new)]]
  return <>
    <MonthStrip onOpen={openMonth} />
    <div className="card"><div className="head"><h2>{d.all ? 'Лиды' : 'Мои лиды'} <span className="muted small">{d.leads.length}</span></h2>
      <button className="ghost mini" disabled={busy} onClick={() => load(true)}>{busy ? '…' : 'Обновить'}</button></div>
      <input value={q} onChange={e => setQ(e.target.value)} placeholder="Имя, телефон, номер" />
      {groups.map(([name, items]) => <div key={name}>
        <div className="dealstage">{name} <span className="muted">· {items.length}</span></div>
        {!items.length && <p className="muted small">Нет.</p>}
        {items.map(l => <div key={l.id} className="qrow" onClick={() => openLead(l.id)}>
          <div className="qmain"><div><b>{l.name}</b> <span className="muted small">№ {l.id}</span></div>
            <div className="small muted">{[l.phone, l.city, l.manager, l.new ? `${Math.max(0, Math.round((Date.now() - new Date(l.created)) / 3600000))} ч назад` : `${ageDays(l.modified)} дн. без движения`].filter(Boolean).join(' · ')}</div>
            {!!l.missing.length && <div>{l.missing.map(m => <span key={m} className="miss">нет: {m}</span>)}</div>}</div>
          <span className="muted">›</span>
        </div>)}
      </div>)}
    </div>
  </>
}

export function LeadCard({ id, back, openDeal }) {
  const [l, setL] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [f, setF] = useState({ city: '', cityName: '', service: '', area: '', sum: '' })
  const [cities, setCities] = useState([])
  const [fail, setFail] = useState(null)
  const load = fresh => api(`/bx/leads/${id}${fresh ? '?fresh=1' : ''}`).then(r => {
    setL(r); setF({ city: r.city_id, cityName: r.city, service: r.service_id, area: r.area || '', sum: r.sum || '' })
  }, e => setErr(e.message))
  useEffect(() => { load(false); api('/bx/leads/cities').then(setCities, () => {}) }, [id])
  if (err) return <div className="card"><a onClick={back}>← назад</a><p className="muted">{err}</p></div>
  if (!l) return <div className="card muted">Загружаю лид № {id}…</div>
  const say = p => p.then(r => { setMsg(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Записано в Битрикс.'); return load(true) }, e => setMsg('Не записалось: ' + e.message))
  const pickCity = v => { const c = cities.find(x => x.name.toLowerCase() === v.trim().toLowerCase()); setF({ ...f, cityName: v, city: c ? c.id : '' }) }
  const save = () => say(api(`/bx/leads/${id}`, { method: 'POST', body: { city: f.city || null, service: f.service || null, area: +f.area || null, sum: +f.sum || null } }))
  const convert = () => api(`/bx/leads/${id}/convert`, { method: 'POST' }).then(r => openDeal(r.deal), e => setMsg('Не получилось: ' + e.message))
  const changed = f.city !== l.city_id || f.service !== l.service_id || (+f.area || 0) !== (l.area || 0) || (+f.sum || 0) !== (l.sum || 0)
  return <>
    <div className="card">
      <a onClick={back}>← к лидам</a>
      <h2>{l.name} <span className="muted small">лид № {l.id}</span></h2>
      <span className="tag">{l.status_name}</span>{l.manager && <span className="tag">{l.manager}</span>}
      {l.title && l.title !== l.name && <p className="small muted">{l.title}</p>}
      <Contact phone={l.phone} name={l.name} entity="lead" id={l.id} />
      <CallOutcome path={`/bx/leads/${id}`} done={() => load(true)} />
    </div>
    <div className="card"><h3>Что нужно для сделки</h3>
      {l.missing.length ? <p className="small">Не хватает: {l.missing.map(m => <span key={m} className="miss">{m}</span>)}</p> : <p className="small ok">Всё заполнено, можно в сделку.</p>}
      <label>Город<input list="lead-cities" value={f.cityName} onChange={e => pickCity(e.target.value)} placeholder="Начните вводить" /></label>
      <datalist id="lead-cities">{cities.map(c => <option key={c.id} value={c.name} />)}</datalist>
      {f.cityName && !f.city && <p className="small muted">Выберите город из списка.</p>}
      {l.has.service && <label>Услуга<select value={f.service} onChange={e => setF({ ...f, service: e.target.value })}>
        <option value="">—</option>{l.services.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>}
      {l.has.area && <label>Площадь, м²<input type="number" min="1" value={f.area} onChange={e => setF({ ...f, area: e.target.value })} /></label>}
      <label>Бюджет, ₸<input type="number" min="0" value={f.sum} onChange={e => setF({ ...f, sum: e.target.value })} /></label>
      {!l.has.service && <p className="small muted">Поля «Услуга» у лида в Битриксе ещё нет — его создаст Кодекс.</p>}
      <button className="ghost" disabled={!changed} onClick={save}>Сохранить в Битрикс</button>
      {msg && <p className="small muted">{msg}</p>}
    </div>
    <div className="card"><h3>Решение</h3>
      <button disabled={!!l.missing.length} onClick={convert}>В сделку</button>
      {!!l.missing.length && <p className="small muted">Кнопка откроется, когда заполнены {l.missing.join(', ')}.</p>}
      {!fail ? <button className="ghost" onClick={() => setFail({ status: l.fail[0]?.id || '', reason: '' })}>Отказ</button>
        : <div className="dealedit">
          <select value={fail.status} onChange={e => setFail({ ...fail, status: e.target.value })}>{l.fail.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
          <input value={fail.reason} onChange={e => setFail({ ...fail, reason: e.target.value })} placeholder="Причина (обязательно)" />
          <div className="dealbtns"><button disabled={!fail.reason.trim()} onClick={() => say(api(`/bx/leads/${id}/status`, { method: 'POST', body: fail })).then(() => setFail(null))}>Закрыть лид</button>
            <button className="ghost" onClick={() => setFail(null)}>Отмена</button></div></div>}
    </div>
    <Feed items={l.feed} />
  </>
}

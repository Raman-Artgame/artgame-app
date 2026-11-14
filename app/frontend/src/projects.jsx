import React, { useEffect, useState } from 'react'
import { Receipt, StatusMark } from './ui.jsx'
import { api, uuid } from './api.js'
import { Skeleton, cleanTitle, money } from './crm.jsx'
import { Gallery } from './objects.jsx'
import { More, shrink } from './work.jsx'
import { DoneBox } from './closing.jsx'
import { ProjChat } from './dm.jsx'

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
  const [chat, setChat] = useState(false)
  const [st, cls] = STATE[x.state]
  const c = x.cond || {}
  const kv = [['Город', x.city], ['Площадь', x.area ? `${x.area} м²` : ''], ['Сложность', x.level || 'МОП ещё не указал'],
    ['Старт', x.start ? dmy(x.start) : ''], ['Сдача', x.due ? dmy(x.due) : ''], ['Смены', x.norm.shifts ? `${x.done.shifts} из ${x.norm.shifts}` : x.done.shifts ? String(x.done.shifts) : ''],
    ['Состав по норме', x.norm.crew ? `${x.norm.crew} чел.` : ''], ['Сделано', x.done.m2 ? `${x.done.m2} м²` : ''], ['МОП', x.manager], ['ГИП', x.gip?.name || '']].filter(([, v]) => v)
  if (chat) return <ProjChat id={x.id} back={() => { setChat(false); if (x.chat) x.chat.unread = 0 }} backText={'← ' + cleanTitle(x.title, x.id)} />
  return <>
    <div className="phero" style={x.cover ? { backgroundImage: `linear-gradient(180deg, rgba(11,11,13,.15), rgba(11,11,13,.85)), url(${x.cover})` } : undefined}>
      <button className="ghost mini back" onClick={back}>← Проекты</button>
      <div><span className={'badge ' + cls}>{st}</span><h1>{cleanTitle(x.title, x.id)}</h1>
        <p className="small">№ {x.id} · {leftText(x)}</p></div>
    </div>
    {x.chat && <button className="pchatbtn" onClick={() => setChat(true)}>
      <b>💬 Чат проекта{+x.chat.unread > 0 && <i className="cnt dmcnt">{x.chat.unread}</i>}</b>
      <span>{x.chat.open ? 'бригада, ГИП, МОП и HEAD' : 'только чтение'} ›</span></button>}
    <div className="card">
      {x.working && <div className={'prog ' + (x.state === 'late' ? 'late' : x.progress >= 100 ? 'ok' : '')}><i style={{ width: pct(x) + '%' }} /></div>}
      <div className="conds light">{COND.map(([k, t]) => <span key={k} className={c[k] ? 'on' : ''}>{c[k] ? '● ' : ''}{t}</span>)}</div>
      {x.address && <a className="route" onClick={() => openUrl(route(x))}>📍 {x.address}<i className="small">Маршрут в 2ГИС ›</i></a>}
      {x.id > 0 && x.contact && <SiteContact id={x.id} c={x.contact} />}
      <div className="kvgrid">{kv.map(([k, v]) => <div key={k}><span>{k}</span><b>{v}</b></div>)}</div>
      {(x.now?.length > 0 || x.people.length > 0) && <><h3>Команда</h3><div className="who">
        {x.now?.map(n => <span key={'n' + n} className="live">● {n}</span>)}
        {x.people.filter(n => !(x.now || []).includes(n)).map(n => <span key={n}>{n}</span>)}</div>
        <p className="small muted">● — смена идёт сейчас; остальные были на объекте последние 4 дня.</p></>}
      {openDeal && <button className="ghost" onClick={() => openDeal(x.id)}>Открыть сделку</button>}
    </div>
    {me && ASSIGN.has(me.role_code) && <GipPick x={x} />}
    {me && x.id > 0 && <Crew id={x.id} />}
    {me && x.id > 0 && <DesignBox id={x.id} me={me} obj={{ id: x.id, title: x.title }} />}
    {me && x.id > 0 && <TripBox id={x.id} />}
    {me && x.id > 0 && MONEY.has(me.role_code) && <MoneyBox id={x.id} />}
    <Gallery obj={{ id: x.id, title: x.title }} me={me} start="photo" skip={['design']} />
    {me && x.id > 0 && (x.working || x.closing) && <DoneBox id={x.id} />}
    {me && (SEE_ALL.has(me.role_code) || (x.gip && x.gip.id === me.id)) && <History id={x.id} mine={x.gip?.id === me.id} />}
  </>
}

// Ссылку из мини-приложения Telegram открываем через openLink — обычная там может не открыться
const openUrl = u => { const t = window.Telegram?.WebApp; if (t?.openLink && t.initData) t.openLink(u); else window.open(u, '_blank', 'noopener') }
const route = x => 'https://2gis.kz/search/' + encodeURIComponent([x.city, x.address].filter(Boolean).join(', '))

// Кто встречает на объекте (HEAD 14.11): имя видят все, телефон и правку — ГИП, МОП и HEAD
function SiteContact({ id, c }) {
  const [v, setV] = useState(c)
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState('')
  const save = () => api(`/objects/${id}/contact`, { method: 'POST', body: f }).then(r => { const n = { ...v, ...r }; Object.assign(c, n); setV(n); setF(null); setMsg('') }, e => setMsg(e.message))
  if (!v.edit && !v.name) return null
  if (f) return <div className="sitec edit">
    <input placeholder="Кто встречает: имя, должность" value={f.name} onChange={e => setF({ ...f, name: e.target.value })} />
    <input placeholder="Телефон" inputMode="tel" value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} />
    {msg && <p className="small why">{msg}</p>}
    <div className="seg"><button className="ghost" onClick={() => setF(null)}>Отмена</button><button onClick={save}>Сохранить</button></div>
  </div>
  return <div className="sitec">
    <div><span className="small muted">Встречает на объекте</span><b>{v.name || 'не указано'}</b></div>
    {v.phone && <a className="mini btnlink" href={'tel:' + v.phone.replace(/[^\d+]/g, '')}>📞 {v.phone}</a>}
    {v.edit && <button className="ghost mini" onClick={() => setF({ name: v.name || '', phone: v.phone || '' })}>{v.name ? 'Изменить' : '+ Указать'}</button>}
  </div>
}

// Деньги проекта (HEAD 14.11) — только HEAD и МОП: сколько стоит, сколько пришло, сколько потратили и что остаётся.
// Оплаты вносятся в сделке; здесь только итог.
const MONEY = new Set(['head', 'mop', 'mop_vip'])
function MoneyBox({ id }) {
  const [m, setM] = useState(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { api(`/objects/${id}/money`).then(setM, () => setM(false)) }, [id])
  if (!m) return null
  const t = n => Math.round(n || 0).toLocaleString('ru-RU') + ' ₸'
  const pct = m.margin == null ? '' : String(m.margin).replace('.', ',') + '%'
  return <div className="card pmoney">
    <h3>Деньги проекта</h3>
    <div className="kvgrid">
      <div><span>Сумма</span><b>{t(m.sum)}</b></div>
      <div><span>Поступило</span><b>{t(m.received)}</b></div>
      <div><span>Долг</span><b className={m.debt > 0 ? 'why' : 'ok'}>{t(m.debt)}</b></div>
      <div><span>Затраты</span><b>{t(m.costs_total)}</b></div>
      <div><span>Прибыль{m.vat_pct ? ' без НДС' : ''}</span><b className={m.profit < 0 ? 'why' : ''}>{t(m.profit)}</b></div>
      <div><span>Маржа</span><b>{pct || '—'}</b></div>
    </div>
    {m.on_check > 0 && <p className="small muted">На сверке у HEAD: {t(m.on_check)}</p>}
    <button className="ghost mini" onClick={() => setOpen(!open)}>{open ? 'Свернуть затраты' : 'Из чего затраты ›'}</button>
    {open && <>{m.costs.map(g => <div key={g.key} className="row"><span>{g.title}</span><b className="nowrap">{t(g.total)}</b></div>)}
      {m.warn.map(w => <p key={w} className="small why">{w}</p>)}</>}
    <p className="small muted">Оплаты вносятся в сделке, шаг «Оплата». Затраты — утверждённые смены и расходы.</p>
  </div>
}

// Дизайн проекта на любой стадии (HEAD 14.11): сложность XS–XL и «+ Дизайн / правка / докидка» → HEAD утверждает → единицы дизайнеру.
const DZ_SEE = new Set(['head', 'lead_designer', 'designer_asst'])
const KIND = { design: 'Дизайн проекта', fix: 'Правка / докидка' }
const DST = { sent: 'у HEAD', approved: 'утверждено', returned: 'вернул' }
function DesignBox({ id, me, obj }) {
  const [d, setD] = useState(null)
  const [f, setF] = useState(null)
  const [msg, setMsg] = useState('')
  const load = () => api(`/design/object/${id}`).then(setD, e => setMsg(e.message))
  useEffect(() => { load() }, [id])
  if (!d) return msg ? <div className="card"><p className="small why">{msg}</p></div> : null
  const units = z => String((d.sizes.find(s => s.code === z) || {}).units ?? '').replace('.', ',')
  const size = z => api(`/design/object/${id}/size`, { method: 'POST', body: { size: z } }).then(r => { setMsg(r.bx.startsWith('error') ? 'В Битрикс не записалось, попробуйте ещё раз' : ''); load() }, e => setMsg(e.message))
  const send = () => api(`/design/object/${id}/extra`, { method: 'POST', body: { ...f, person_id: +f.person_id } }).then(() => { setF(null); setMsg(''); load() }, e => setMsg(e.message))
  const dz = DZ_SEE.has(me.role_code)
  if (!dz) return <div className="card dzbox"><h3>Дизайн</h3><Gallery obj={obj} me={me} only={['design']} bare /></div>
  return <div className="card dzbox">
    <div className="head"><h3>Дизайн</h3>{d.can_edit && !f && <button className="mini" onClick={() => setF({ kind: d.rows.some(r => r.kind === 'design') ? 'fix' : 'design', size: 'xs', person_id: d.team[0]?.id || '', note: '', url: '' })}>+ Добавить</button>}</div>
    <label className="muted">Сложность дизайна</label>
    <div className="chips">{d.sizes.map(s => <button key={s.code} disabled={!d.can_edit} className={d.size === s.code ? 'on' : 'ghost'} onClick={() => size(s.code)}>{s.code.toUpperCase()}</button>)}</div>
    {!d.size && <p className="small muted">{d.can_edit ? 'Не указана — выберите размер.' : 'Главный дизайнер ещё не указал.'}</p>}
    {f && <div className="warnbox">
      <div className="segf">{Object.entries(KIND).map(([k, t]) => <button key={k} className={f.kind === k ? 'on' : ''} onClick={() => setF({ ...f, kind: k })}>{t}</button>)}</div>
      <label className="muted">Кто делал</label>
      <select value={f.person_id} onChange={e => setF({ ...f, person_id: e.target.value })}>{d.team.map(t => <option key={t.id} value={t.id}>{t.full_name}</option>)}</select>
      <label className="muted">Размер работы</label>
      <div className="chips">{d.sizes.map(s => <button key={s.code} className={f.size === s.code ? 'on' : 'ghost'} onClick={() => setF({ ...f, size: s.code })}>{s.code.toUpperCase()} · {units(s.code)}</button>)}</div>
      <textarea rows="2" placeholder={f.kind === 'fix' ? 'Что поправили или докинули на объекте' : 'Что сделали: эскиз, файлы в печать…'} value={f.note} onChange={e => setF({ ...f, note: e.target.value })} />
      <input placeholder="Ссылка на файл или папку (по желанию)" value={f.url} onChange={e => setF({ ...f, url: e.target.value })} />
      <div className="seg"><button className="ghost" onClick={() => setF(null)}>Отмена</button><button disabled={f.note.trim().length < 3 || !f.person_id} onClick={send}>На утверждение HEAD</button></div>
    </div>}
    {msg && <p className="small why">{msg}</p>}
    {d.rows.map(r => <div key={r.id} className="row">
      <div><b>{KIND[r.kind]} · {r.size.toUpperCase()}</b>
        <div className="small muted">{[r.person_name, r.note].join(' · ')}</div>
        {r.reason && <div className="small why">HEAD: {r.reason}</div>}</div>
      <div className="qbtns"><span className={'small ' + (r.status === 'approved' ? 'ok' : r.status === 'returned' ? 'why' : 'muted')}>{DST[r.status]}{r.status === 'approved' ? ` · ${String(+r.units).replace('.', ',')} ед.` : ''}</span></div>
    </div>)}
    {d.can_edit && <p className="small muted">Правки и докидки на объекте вносите здесь. Единицы дизайнеру — после «утверждаю» HEAD.</p>}
    <h3 className="sub">Эскизы и файлы в печать</h3>
    <Gallery obj={obj} me={me} only={['design']} bare />
  </div>
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

// Команда объекта (HEAD 09.11: «Где главный художник назначает на объект?»): ставят ГИП, Главный, Про, Мастер печати, МОП и HEAD.
// Назначенному приходит сообщение бота, объект у него первым в «Смене».
function Crew({ id }) {
  const [d, setD] = useState(null)
  const [add, setAdd] = useState(0)
  const [msg, setMsg] = useState('')
  useEffect(() => { api(`/objects/${id}/crew`).then(setD, () => setD({ crew: [], can_edit: false })) }, [id])
  if (!d || (!d.crew.length && !d.can_edit)) return null
  const set = (pid, on) => api(`/objects/${id}/crew`, { method: 'POST', body: { person_id: pid, on } })
    .then(r => { setD({ ...d, crew: r.crew }); setAdd(0); setMsg(on ? 'Поставлен на объект, ему пришло сообщение.' : 'Снят с объекта.') }, e => setMsg(e.message))
  const free = (d.candidates || []).filter(c => !d.crew.some(x => x.id === c.id))
  return <div className="card crew"><h3>На объекте работают</h3>
    {d.crew.length ? <div className="who">{d.crew.map(c => <span key={c.id}>{c.full_name} <i className="small muted">· {c.role_title}</i>
      {d.can_edit && <a className="x" aria-label="снять" onClick={() => confirm(`Снять ${c.full_name} с объекта?`) && set(c.id, false)}> ✕</a>}</span>)}</div>
      : <p className="small muted">Пока никого не поставили.</p>}
    {d.can_edit && <div className="seg"><select value={add} onChange={e => setAdd(+e.target.value)}>
      <option value={0}>— кого поставить —</option>
      {free.map(c => <option key={c.id} value={c.id}>{c.full_name} · {c.role_title}</option>)}</select>
      <button className="mini" disabled={!add} onClick={() => set(add, true)}>Поставить</button></div>}
    <p className="small muted">{msg || (d.can_edit ? 'Назначенный получит сообщение, объект у него станет первым в «Смене».' : 'Состав ставят ГИП и главные.')}</p></div>
}

// Командировка (HEAD 10.11): галочка в проекте → пункты расходов (проживание, дорога, транспорт на месте, прочее).
// Питание — само, pay.trip_food за каждый день смены или дороги каждого на объекте; при смене галочки смены пересчитываются.
function TripBox({ id }) {
  const [d, setD] = useState(null)
  const [add, setAdd] = useState(null)
  const [msg, setMsg] = useState('')
  useEffect(() => { api(`/objects/${id}/trip-costs`).then(setD, () => setD(false)) }, [id])
  if (!d || (!d.on && !d.can_edit)) return null
  const setTrip = v => api(`/objects/${id}/trip-set`, { method: 'POST', body: { trip: v } })
    .then(r => { setD(r); setMsg(r.retrip ? `Пересчитал смен: ${r.retrip}.` : '') }, e => setMsg(e.message))
  const save = () => api(`/objects/${id}/trip-costs`, { method: 'POST', body: { client_uid: uuid(), item: add.item, amount: +add.amount,
    note: add.note || null, paid_by: add.paid_by, receipt: add.receipt || null } }).then(r => { setD(r); setAdd(null); setMsg('Записано.') }, e => setMsg(e.message))
  const by = Object.fromEntries(d.items.map(i => [i.code, d.costs.filter(c => c.category === i.code)]))
  return <div className="card trip"><div className="head"><h3>Командировка</h3>{d.on && <b className="nowrap">{money(d.total)}</b>}</div>
    {d.can_edit && <div className="chips">{[[true, 'Да, выезд'], [false, 'Нет'], [null, 'По городу']].map(([v, t]) =>
      <button key={String(v)} className={d.trip === v ? 'on' : ''} onClick={() => setTrip(v)}>{t}</button>)}</div>}
    {!d.on ? <p className="small muted">Не командировка{d.trip === null ? ' (по городу сотрудников и объекта)' : ''}.</p> : <>
      <div className="row"><div><b>Питание</b><div className="small muted">{d.food.rate ? `${d.food.days} чел.-дней × ${money(d.food.rate)} — начисляется в ФОТ само` : 'Ставки питания нет в «Значениях»'}</div></div>{d.food.rate ? <b className="nowrap">{money(d.food.amount)}</b> : null}</div>
      {d.items.map(i => <div key={i.code} className="row"><div><b>{i.title}</b>
        {by[i.code].map(c => <div key={c.id} className="small muted">{money(+c.amount)} · {c.paid_by === 'company' ? 'компании' : 'свои'} · {c.person}{c.note ? ' · ' + c.note : ''}
          {c.status === 'submitted' ? ' · у HEAD' : c.status === 'rejected' ? ' · отклонено' : ''}{c.receipt_url ? <> · <a href={c.receipt_url}>чек</a></> : ''}</div>)}
        {!by[i.code].length && <div className="small muted">не внесено</div>}</div>
        {d.can_edit && <button className="ghost mini" onClick={() => setAdd({ item: i.code, amount: '', note: '', paid_by: 'company', receipt: '' })}>+ сумма</button>}</div>)}
      {add && <div className="dealedit"><b>{d.items.find(i => i.code === add.item).title}</b>
        <input inputMode="numeric" placeholder="Сумма, ₸" value={add.amount} onChange={e => setAdd({ ...add, amount: e.target.value.replace(/\D/g, '') })} />
        <input placeholder="Комментарий (3 ночи, билеты туда-обратно…)" value={add.note} onChange={e => setAdd({ ...add, note: e.target.value })} />
        <div className="seg"><button className={add.paid_by === 'company' ? '' : 'ghost'} onClick={() => setAdd({ ...add, paid_by: 'company' })}>Компании</button>
          <button className={add.paid_by === 'own' ? '' : 'ghost'} onClick={() => setAdd({ ...add, paid_by: 'own' })}>Свои деньги</button></div>
        <Receipt value={add.receipt} pick={async f => setAdd({ ...add, receipt: await shrink(f) })} />
        <div className="seg"><button disabled={!(+add.amount > 0)} onClick={save}>Записать</button><button className="ghost" onClick={() => setAdd(null)}>Отмена</button></div></div>}</>}
    {msg && <p className="small muted">{msg}</p>}
  </div>
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
      <StatusMark status={s.status} /></div>)}</>}
    {h.expenses.length > 0 && <><h3>Расходы · {money(h.spent)}</h3>{h.expenses.map(e => <div key={e.id} className="row">
      <div><b>{money(e.amount)}</b> · {e.category} · {e.full_name}<br /><span className="small muted">{dt(e.created_at)}{e.note ? ' · ' + e.note : ''}</span>
        {e.receipt_url && <a href={e.receipt_url} target="_blank" rel="noreferrer"> чек</a>}</div>
      <StatusMark status={e.status} /></div>)}</>}
  </div>
}

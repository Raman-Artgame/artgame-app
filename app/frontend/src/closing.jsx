import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Sheet } from './ui.jsx'
import { Skeleton, cleanTitle } from './crm.jsx'

// Закрытие сделки через HEAD (HEAD 12.11 «Да, по рекомендациям»). МОП: шаг «Закрытие» в карточке сделки — 12 пунктов (12-й — Продакшн, HEAD 12.11)
// (их проверяет приложение) и кнопка «На закрытие». HEAD: заявки на Пульте, паспорт сделки, «Закрыть» или «Вернуть».
const tg = n => Math.round(n || 0).toLocaleString('ru-RU') + ' ₸'
const dm = s => s ? s.slice(0, 10).split('-').reverse().join('.') : '—'
const today = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Almaty' })
const READY = 'UC_BMKDS4'
const pct = v => v == null ? '—' : (+v).toLocaleString('ru-RU', { maximumFractionDigits: 1 }) + '%'
const plural = (n, a, b, c) => { const m = Math.floor(Math.abs(n)); return m % 10 === 1 && m % 100 !== 11 ? a : m % 10 >= 2 && m % 10 <= 4 && (m % 100 < 12 || m % 100 > 14) ? b : c }
const num = v => (+v || 0).toLocaleString('ru-RU', { maximumFractionDigits: 1 })

// Пункты закрытия: что не выполнено — сверху, с тем, где и кто делает; выполненные свёрнуты в одну строку
function Checks({ list, full }) {
  const [all, setAll] = useState(false)
  const good = list.filter(x => x.ok)
  const show = all ? list : list.filter(x => !x.ok)
  return <div className="cklist">{show.map(x => <div key={x.key} className={'ck' + (x.ok ? ' ok' : ' bad') + (x.skip ? ' skip' : '')}>
    <i aria-hidden="true">{x.skip ? '–' : x.ok ? '✓' : '✕'}</i>
    <div><b>{x.title}</b><span className="small">{x.detail}</span>
      {!x.ok && (full !== false) && <span className="small where">{x.where} · {x.who}</span>}</div>
  </div>)}
    {good.length > 0 && <button className="ckmore" onClick={() => setAll(!all)}><i aria-hidden="true">✓</i>
      {all ? 'Свернуть выполненные' : good.length === list.length ? `Все ${list.length} ${plural(list.length, 'пункт выполнен', 'пункта выполнены', 'пунктов выполнены')} · показать`
        : `Выполнено: ${good.length} · показать`}</button>}
  </div>
}

// «Работы сданы» (окончание работ, факт): ГИП объекта, МОП и HEAD. В Битрикс дата уходит при закрытии сделки.
export function DoneBox({ id, onSaved, compact }) {
  const [d, setD] = useState(null)
  const [day, setDay] = useState('')
  const [msg, setMsg] = useState('')
  const load = () => api(`/objects/${id}/done`).then(x => { setD(x); setDay(x.done_on || x.last_shift || '') }, () => setD(false))
  useEffect(() => { load() }, [id])
  if (!d || (!compact && !d.can_edit && !d.done_on)) return null
  const save = v => api(`/objects/${id}/done`, { method: 'POST', body: { day: v || null } })
    .then(x => { setD(x); setMsg(v ? 'Отмечено. Дата уйдёт в сделку при закрытии.' : 'Отметка снята.'); onSaved && onSaved() }, e => setMsg(e.message))
  const body = <>
    {d.done_on ? <p className="small">Работы сданы <b>{dm(d.done_on)}</b>{d.done_by ? ` · отметил ${d.done_by}` : ''}</p>
      : <p className="small muted">Дата сдачи ещё не отмечена{d.last_shift ? ` · последняя смена ${dm(d.last_shift)}` : ''}.</p>}
    {d.can_edit && <div className="donerow"><input type="date" value={day} max={today()} onChange={e => setDay(e.target.value)} aria-label="Дата сдачи" />
      <button className="mini" disabled={!day || day === d.done_on} onClick={() => save(day)}>{d.done_on ? 'Изменить' : 'Работы сданы'}</button></div>}
    {msg && <p className="small muted">{msg}</p>}
  </>
  return compact ? body : <div className="card"><h3>Сдача объекта</h3>{body}
    <p className="small muted">Отмечает ГИП в день сдачи. По этой дате — выручка месяца и срок в паспорте сделки.</p></div>
}

// Шаг «Закрытие» в карточке сделки
export function ClosePanel({ d, onDone }) {
  const [s, setS] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [pass, setPass] = useState(false)
  const load = () => api(`/bx/deals/${d.id}/close`).then(setS, e => setErr(e.message))
  useEffect(() => { load() }, [d.id, d.stage])
  if (err) return <div className="card"><h3>Закрытие</h3><p className="small muted">{err}</p></div>
  if (!s) return <div className="card"><Skeleton n={2} /></div>
  if (pass) return <Passport id={d.id} back={() => { setPass(false); load() }} onDecided={t => { setPass(false); onDone(t) }} />
  const rq = s.request
  const miss = s.checks.filter(x => !x.ok)
  const sent = rq?.status === 'sent'
  const closed = rq?.status === 'closed' || s.won
  const send = () => { setBusy(true); setErr('')
    api(`/bx/deals/${d.id}/close`, { method: 'POST' }).then(() => { setBusy(false); load(); onDone('Заявка ушла HEAD: паспорт сделки у него на Пульте.') }, e => { setBusy(false); setErr(e.message) }) }
  return <div className="card closepanel">
    <div className="panelhead"><h3>Закрытие сделки</h3><span className={'badge ' + (closed ? 'ok' : sent ? 'warn' : miss.length ? '' : 'ok')}>
      {closed ? 'закрыта' : sent ? 'у HEAD' : `${s.checks.length - miss.length} из ${s.checks.length}`}</span></div>
    {closed && <div className="hint"><div><b>{rq?.status === 'closed' ? `Закрыта HEAD ${dm(rq.decided_at)}` : 'Сделка в «Оплата получена»'}</b><br />
      {rq?.status === 'closed' ? 'Паспорт сохранён, смены и расходы на объект больше не вносятся.' : 'Паспорта нет: сделку перевели в Битриксе, HEAD видит её на Пульте.'}</div></div>}
    {sent && <div className="hint"><div><b>На закрытии у HEAD с {dm(rq.sent_at)}</b><br />Отправил {rq.sent_by}. Решение придёт в «Чат» → «HEAD».</div></div>}
    {rq?.status === 'returned' && !closed && <div className="lockbox"><b>↩️ HEAD вернул {dm(rq.decided_at)}</b>
      {rq.reason && <div>{rq.reason}</div>}
      {rq.points?.length > 0 && <div>{rq.points.map(x => <span key={x.key} className="miss">{x.title}</span>)}</div>}
      <div className="small" style={{ marginTop: 6 }}>Доделайте и отправьте снова.</div></div>}
    {!closed && !sent && !s.ready && <p className="small muted">«На закрытие» — со стадии «Оплата+закрывающие документы», когда работы сданы. Ниже — что приложение проверит.</p>}
    {s.no_docs && <p className="small muted">Сделка «Без документов (наличные/перевод)»: договор, счёт и АВР не нужны.</p>}
    {s.test && <p className="small why">Тестовая сделка — её не закрываем.</p>}
    <Checks list={s.checks} />
    {!closed && s.object && (!s.checks.find(x => x.key === 'end')?.ok || (rq?.status === 'returned' && rq.points?.some(x => x.key === 'end'))) &&
      <DoneBox id={d.id} compact onSaved={load} />}
    {!closed && !sent && !s.head && s.ready && !s.test && (miss.length ? <div className="lockbox"><b>🔒 «На закрытие» откроется, когда будет готово:</b>
      <div>{miss.map(x => <span key={x.key} className="miss">{x.short || x.title}</span>)}</div></div>
      : <button disabled={busy} onClick={send}>{busy ? 'Отправляю…' : 'На закрытие'}</button>)}
    {!s.head && !closed && !sent && <p className="small muted">В «Оплата получена» сделку переводит только HEAD — после проверки паспорта сделки.</p>}
    {s.head && !s.test && <button className={closed ? 'ghost' : ''} onClick={() => setPass(true)}>{closed ? 'Паспорт сделки' : sent ? 'Открыть заявку · паспорт сделки' : miss.length ? 'Паспорт сделки' : 'Паспорт сделки · закрыть'}</button>}
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
  </div>
}

function Group({ g }) {
  const [open, setOpen] = useState(false)
  const [rc, setRc] = useState(false)
  return <div className="cgroup">
    <div className="row" onClick={() => setOpen(!open)} role="button"><span><b>{g.title}</b>{g.rows.length ? <span className="muted small"> · {g.rows.length}</span> : null}</span>
      <span><b>{tg(g.total)}</b> <span className="muted">{open ? '▴' : '▾'}</span></span></div>
    {open && <div className="crows">
      {!g.rows.length && <p className="small muted">нет</p>}
      {g.rows.map((x, i) => <div key={i} className="crow"><div><span>{x.name}</span><span className="small muted">
        {[x.role, x.shifts != null ? `${x.shifts} ${plural(x.shifts, 'смена', 'смены', 'смен')} · ${num(x.hours)} ч` : '', x.count ? `${x.count} ${plural(x.count, 'запись', 'записи', 'записей')}` : '', x.note]
          .filter(Boolean).join(' · ')}</span></div><b>{tg(x.sum)}</b></div>)}
      {g.items?.length > 0 && <><a className="small" onClick={() => setRc(!rc)}>{rc ? 'Скрыть чеки' : `Чеки и записи · ${g.items.length}`}</a>
        {rc && g.items.map(x => <div key={x.id} className="crow"><div><span>{x.title} · {x.person}</span><span className="small muted">{dm(x.day)}{x.paid_by === 'own' ? ' · свои' : ''}{x.note ? ' · ' + x.note : ''}</span></div>
          <span className="cval"><b>{tg(x.amount)}</b>{x.receipt_url ? <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a> : <span className="small muted">без чека</span>}</span></div>)}</>}
    </div>}
  </div>
}

// Паспорт сделки (только HEAD): всё о сделке на одном экране и решение «Закрыть» / «Вернуть»
export function Passport({ id, back, onDecided }) {
  const [p, setP] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  const [ret, setRet] = useState(false)
  const [msg, setMsg] = useState('')
  const load = () => api(`/head/closing/${id}`).then(setP, e => setErr(e.message))
  useEffect(() => { load() }, [id])
  if (err && !p) return <div className="card"><a onClick={back}>← назад</a><p className="muted">{err}</p></div>
  if (!p) return <Skeleton n={4} />
  const dl = p.deal, m = p.money, r = p.result, pl = p.plan, dt = dl.dates
  const bad = (p.checks || []).filter(x => !x.ok)
  const close = () => { setBusy('close'); setErr('')
    api(`/head/closing/${id}/close`, { method: 'POST' }).then(x => { setBusy(''); onDecided ? onDecided(x.bx === 'off' ? 'Закрыта в приложении, в Битрикс не записано.' : 'Сделка закрыта: «Оплата получена», паспорт сохранён, PDF — в «ДОКУМЕНТЫ».') : load() },
      e => { setBusy(''); setErr(e.message) }) }
  const prod = f => api(`/head/closing/${id}/prod/${f.id}`, { method: 'POST' }).then(() => { setMsg('Фото в «МЕДИА / Продакшн / Фото».'); load() }, e => setMsg(e.message))
  const pdf = () => { setBusy('pdf'); api(`/head/closing/${id}/pdf`, { method: 'POST' }).then(() => { setBusy(''); load() }, e => { setBusy(''); setMsg(e.message) }) }
  const client = !dl.client ? '—' : dl.client_type && !dl.client.includes(dl.client_type) ? `${dl.client} · ${dl.client_type}` : dl.client
  const kv = [['Клиент', client], ['Исполнитель', dl.myco], ['МОП', dl.mop || '—'], ['ГИП', dl.gip || '—'],
    ['Город', dl.city || '—'], ...(dl.object ? [['Объект', dl.object]] : []), ['Площадь', dl.area ? `${num(dl.area)} м²` : '—'], ['Услуга', dl.service || '—'],
    ['Договор', dm(dt.signed)], ['Старт', dm(dt.start)], ['Сдача, план', dm(dt.end_plan)], ['Сдача, факт', dm(dt.end_fact)]]
  const low = r.model != null && r.margin != null && r.margin < r.model
  return <>
    <div className="card dark passhero">
      <a className="back" onClick={back}>← назад</a>
      <span className="small muted">Паспорт сделки</span>
      <h2>№ {dl.id} · {cleanTitle(dl.title, dl.id)}</h2>
      <span className="tag">{dl.myco}</span>{p.frozen && <span className="tag okt">закрыта {dm(p.closed?.at)} · {p.closed?.by}</span>}
      {p.bypass && !p.frozen && <span className="tag hott">закрыта в Битриксе мимо паспорта</span>}
      <div className="passnums">
        <div><span>Прибыль</span><b className={r.profit < 0 ? 'neg' : ''}>{tg(r.profit)}</b></div>
        <div><span>Маржа</span><b className={low ? 'neg' : 'pos'}>{pct(r.margin)}</b>{r.model != null && <em>норма {pct(r.model)}</em>}</div>
        <div><span>Выручка без НДС</span><b>{tg(r.net)}</b></div>
        <div><span>Затраты</span><b>{tg(r.costs)}</b></div>
      </div>
    </div>

    {p.flags.length > 0 && <div className="card flags"><h3>Красные флаги · {p.flags.length}</h3>
      {p.flags.map((f, i) => <div key={i} className="flag">{f}</div>)}</div>}

    {!p.frozen && <div className="card decide">
      {p.request?.status === 'sent' && <p className="small">На закрытие отправил {p.request.sent_by} · {dm(p.request.sent_at)}</p>}
      {p.request?.status === 'returned' && <p className="small muted">Последний раз вернули {dm(p.request.decided_at)}{p.request.reason ? `: ${p.request.reason}` : ''}</p>}
      {!p.ready && !p.won && <p className="small muted">Сделка не на «Оплата+закрывающие документы» — закрыть пока нельзя.</p>}
      {(p.ready || p.won) && bad.length > 0 && <div className="lockbox"><b>🔒 {p.bypass ? '«Принять закрытие»' : '«Закрыть»'} откроется, когда будут выполнены все пункты</b>
        <div>Не выполнено {bad.length} из {p.checks.length}:</div><div>{bad.map(x => <span key={x.key} className="miss">{x.short || x.title}</span>)}</div></div>}
      <div className="dealbtns wrapbtns">
        {(p.ready || p.won) && !bad.length && <button disabled={!!busy || p.test} onClick={close}>{busy === 'close' ? 'Закрываю…' : p.bypass ? 'Принять закрытие' : 'Закрыть'}</button>}
        <button className={bad.length ? '' : 'ghost'} disabled={!!busy} onClick={() => setRet(true)}>{p.bypass ? 'Вернуть на «Оплата+закрывающие»' : 'Вернуть'}</button>
      </div>
      <p className="small muted">{(p.bypass ? '«Вернуть» — сделка назад на «Оплата+закрывающие документы», МОП и ГИП получат список, что доделать.'
        : '«Вернуть» — МОП и ГИП получат список, что доделать.') + (bad.length ? '' : p.bypass ? ' «Принять» — паспорт сохранится, в Битриксе ничего не меняется.'
        : ' «Закрыть» — сделка уйдёт в «Оплата получена», паспорт сохранится, PDF ляжет в «ДОКУМЕНТЫ». Прибыль и маржа в Битрикс не пишутся.')}</p>
      {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
    </div>}
    {p.frozen && <div className="card"><h3>Закрытие</h3>
      <p className="small">Закрыл {p.closed?.by} · {dm(p.closed?.at)}{p.closed?.via === 'bitrix' ? ' · сделку перевели в Битриксе, паспорт принят' : ''}</p>
      {p.request?.pdf ? <a className="btn ghost" href={p.request.pdf} target="_blank" rel="noreferrer">PDF паспорта в «ДОКУМЕНТЫ»</a>
        : <><p className="small why">{p.request?.pdf_error ? 'PDF не сохранился: Диск не ответил.' : 'PDF сохраняется…'}</p>
          {p.request?.pdf_error && <button className="ghost mini" disabled={!!busy} onClick={pdf}>Сохранить PDF ещё раз</button>}</>}
    </div>}

    <div className="card"><h3>Пункты закрытия</h3><Checks list={p.checks || []} full={!p.frozen} /></div>

    <div className="card"><h3>Сделка</h3>
      <div className="kvgrid">{kv.map(([k, v]) => <div key={k}><span>{k}</span><b>{v}</b></div>)}</div></div>

    <div className="card"><h3>Деньги</h3>
      <div className="kv">
        <div><span className="muted small">Сумма с НДС</span><b>{tg(m.sum)}</b></div>
        <div><span className="muted small">Без НДС ({m.vat_pct}%)</span><b>{tg(m.net)}</b></div>
        <div><span className="muted small">Поступило</span><b>{tg(m.received)}</b></div>
        <div><span className="muted small">Долг</span><b className={m.debt ? 'neg' : ''}>{tg(m.debt)}</b></div>
      </div>
      {m.items.map(x => <div key={x.id} className="crow"><div><span>{dm(x.op_date)} · {x.account_title}</span>
        <span className="small muted">{[x.source === 'app' ? `внёс ${x.author || 'МОП'}` : x.source === 'bitrix' ? 'из поля сделки' : 'HEAD', x.on_check ? 'на сверке' : ''].filter(Boolean).join(' · ')}</span></div>
        <span className="cval"><b>{tg(x.amount)}</b>{x.receipt_url ? <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a> : <span className="small muted">без чека</span>}</span></div>)}
      {m.history?.length > 0 && <p className="small muted">До ноября: {m.history.map(h => `${tg(h.amount)}${h.date ? ' · ' + dm(h.date) : ''}`).join(', ')}</p>}
    </div>

    <div className="card"><div className="panelhead"><h3>Затраты</h3><b>{tg(p.costs_total)}</b></div>
      {p.costs.map(g => <Group key={g.key} g={g} />)}</div>

    <div className="card"><h3>План и факт</h3>
      <div className="kvgrid">
        <div><span>Срок, дней</span><b>{pl.days ?? '—'}{pl.term ? ` · план ${num(pl.term)}` : ''}</b></div>
        <div><span>Смены</span><b>{pl.shifts_fact}{pl.shifts_plan ? ` · по расчёту ${num(pl.shifts_plan)}` : ''}</b></div>
      </div></div>

    <div className="card"><h3>Документы и медиа</h3>
      <div className="chips docchips">{p.docs.map(x => <span key={x.title} className={'tag' + (x.n ? '' : ' none')}>{x.title}{x.n ? ` · ${x.n}` : ' · нет'}</span>)}</div>
      {p.photos.length > 0 ? <div className="grid passph">{p.photos.map(f => <div key={f.id} className="ph">
        <a href={f.url} target="_blank" rel="noreferrer"><img src={f.thumb} alt={f.name} loading="lazy" /></a>
        {f.prod ? <span className="badge ok">в Продакшн</span> : !p.frozen ? <button className="ghost mini" onClick={() => prod(f)}>В Продакшн</button> : null}</div>)}</div>
        : <p className="small muted">Фото объекта нет.</p>}
      {p.photos_total > p.photos.length && <p className="small muted">Последние {p.photos.length} из {p.photos_total} — остальные в папке сделки.</p>}
      {msg && <p className="small muted">{msg}</p>}
      <div className="dealbtns wrapbtns">
        {p.folder && <a className="btn ghost mini" href={p.folder} target="_blank" rel="noreferrer">Папка сделки на Диске</a>}
        {p.bitrix && <a className="btn ghost mini" href={p.bitrix} target="_blank" rel="noreferrer">Сделка в Битриксе</a>}
      </div></div>
    {ret && <ReturnSheet id={id} p={p} onClose={() => setRet(false)} onDone={t => { setRet(false); onDecided ? onDecided(t) : load() }} />}
  </>
}

function ReturnSheet({ id, p, onClose, onDone }) {
  const [pts, setPts] = useState(() => (p.checks || []).filter(x => !x.ok).map(x => x.key))
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const flip = k => setPts(pts.includes(k) ? pts.filter(x => x !== k) : [...pts, k])
  const send = () => { setBusy(true)
    api(`/head/closing/${id}/return`, { method: 'POST', body: { reason: reason.trim() || null, points: pts } })
      .then(x => onDone(`Вернули на доработку: сообщение ушло МОП и ГИП (${x.told}).`), e => { setBusy(false); setErr(e.message) }) }
  return <Sheet title="Вернуть на доработку" onClose={onClose}>
    <p className="small muted">Отметьте, что доделать, или напишите причину. МОП и ГИП получат список в «Чат» → «HEAD».</p>
    <div className="chips">{(p.checks || []).map(x => <button key={x.key} className={pts.includes(x.key) ? 'on' : ''} onClick={() => flip(x.key)}>{x.short || x.title}</button>)}</div>
    <textarea rows={3} value={reason} onChange={e => setReason(e.target.value)} placeholder="Причина: что не так" />
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
    <button disabled={busy || (!pts.length && !reason.trim())} onClick={send}>{busy ? 'Отправляю…' : 'Вернуть МОП и ГИП'}</button>
  </Sheet>
}

// Вкладка HEAD «Закрытие»: заявки МОП, закрытые мимо паспорта, последние закрытые
export function Closing({ initial }) {
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(initial || null)
  const [toast, setToast] = useState('')
  const load = () => api('/head/closing').then(setD, e => setD({ error: e.message, sent: [], bypass: [], closed: [] }))
  useEffect(() => { load() }, [])
  if (open) return <Passport id={open} back={() => { setOpen(null); load() }} onDecided={t => { setOpen(null); setToast(t); load(); setTimeout(() => setToast(''), 6000) }} />
  if (!d) return <Skeleton n={3} />
  const row = (x, k, sub, cls) => <div key={k + x.deal_id} className={'qrow' + (cls ? ' ' + cls : '')} onClick={() => setOpen(x.deal_id)}>
    <div className="qmain"><b>№ {x.deal_id} · {cleanTitle(x.title, x.deal_id)}</b><div className={'small ' + (cls ? 'why' : 'muted')}>{sub}</div></div><span className="muted">›</span></div>
  return <>
    {toast && <div className="toast">{toast}</div>}
    <div className="card"><h2>Закрытие сделок</h2>
      <p className="small muted">МОП отправляет сделку «На закрытие», когда выполнены все пункты, в том числе Продакшн. В «Оплата получена» её переводите вы — кнопкой «Закрыть» в паспорте. Пока хоть один пункт не выполнен, закрыть нельзя.</p>
      {d.error && <p className="small why">{d.error}</p>}</div>
    <div className="card"><h3>Ждут решения · {d.sent.length}</h3>
      {!d.sent.length && <p className="small muted">Заявок нет.</p>}
      {d.sent.map(x => row(x, 's', `${tg(x.amount)} · ${x.sent_by || 'МОП'} · ${dm(x.sent_at)}`))}</div>
    {d.bypass.length > 0 && <div className="card bypass"><h3>Закрыты мимо вас · {d.bypass.length}</h3>
      <p className="small muted">Перевели в «Оплата получена» прямо в Битриксе. Назад сами не двигаются: откройте паспорт. Принять можно, только когда выполнены все пункты, иначе — вернуть.</p>
      {d.bypass.map(x => row(x, 'b', `${tg(x.amount)} · ${dm(x.moved)}${x.moved_by ? ' · перевёл ' + x.moved_by : ''}`, 'hot'))}</div>}
    <div className="card"><h3>Закрытые</h3>
      {!d.closed.length && <p className="small muted">Пока ни одной.</p>}
      {d.closed.map(x => row(x, 'c', `${tg(x.amount)} · ${dm(x.decided_at)}${x.result?.margin != null ? ` · маржа ${pct(x.result.margin)}` : ''}${x.via === 'bitrix' ? ' · мимо паспорта' : ''}`))}</div>
  </>
}

// Для Пульта: заявки на закрытие и закрытые мимо паспорта
export function useClosing(on) {
  const [c, setC] = useState(null)
  useEffect(() => { if (on) api('/head/closing').then(setC, () => setC(null)) }, [on])
  return c
}

export const closeAsks = c => c ? [
  c.bypass?.length && { k: 'closing', t: `Закрыты мимо вас в Битриксе: ${c.bypass.length}`, s: c.bypass.map(x => '№ ' + x.deal_id).join(', ') + ' · принять или вернуть', hot: true, red: true },
  c.sent?.length && { k: 'closing', t: `Сделки на закрытие: ${c.sent.length}`, s: c.sent.map(x => `№ ${x.deal_id} · ${tg(x.amount)}`).join(', ') + ' · паспорт сделки' },
].filter(Boolean) : []

export { READY }

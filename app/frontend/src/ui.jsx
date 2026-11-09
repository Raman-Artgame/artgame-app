import React, { useEffect, useState } from 'react'

// Всплывающее окно (HEAD 06.11): лист снизу на телефоне, окно по центру на компьютере. Закрывается тапом по фону, ✕ и Esc.
export function Sheet({ title, onClose, children, wide }) {
  useEffect(() => {
    const k = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', k); document.body.style.overflow = prev }
  }, [])
  return <div className="sheet" onClick={onClose}>
    <div className={'sheetbox modal' + (wide ? ' wide' : '')} onClick={e => e.stopPropagation()} role="dialog" aria-modal="true">
      <div className="mhead"><h2>{title}</h2><button className="x" aria-label="Закрыть" onClick={onClose}>✕</button></div>
      <div className="mbody">{children}</div>
    </div>
  </div>
}

// Кнопка «Скопировать»: копирует текст и на полторы секунды пишет «Скопировано».
export function Copy({ text, label = 'Скопировать', className = 'ghost mini' }) {
  const [ok, setOk] = useState('')
  const go = () => navigator.clipboard?.writeText(text).then(() => setOk('Скопировано'), () => setOk('Не удалось')).finally(() => setTimeout(() => setOk(''), 1500))
  return <button className={className} onClick={go}>{ok || label}</button>
}

// Выбор города (HEAD 06.11: город обязателен и главный): частые города — кнопками, остальные — поиском по началу слова.
// «Астана» находит «Астана (Нур-Султан)»; без выбора из списка город не засчитывается (в Битриксе это список).
export const cityBase = n => (n || '').split(' (')[0]
const TOP_CITIES = ['Астана', 'Алматы', 'Шымкент']
export function CityPicker({ cities, value, onPick, label = 'Город', need, wide }) {
  const cur = (cities || []).find(c => c.id === value)
  const [q, setQ] = useState('')
  const [edit, setEdit] = useState(false)
  const s = q.trim().toLowerCase()
  const starts = c => cityBase(c.name).toLowerCase().startsWith(s)
  const hits = s ? [...cities.filter(starts), ...cities.filter(c => !starts(c) && c.name.toLowerCase().includes(s))].slice(0, 6) : []
  const top = TOP_CITIES.map(t => cities.find(c => cityBase(c.name) === t)).filter(Boolean)
  const pick = c => { onPick(c.id, c.name); setQ(''); setEdit(false) }
  return <div className={'citypick' + (need && !cur ? ' need' : '') + (wide ? ' wide' : '')}>
    <span className="cplabel">{label}{need && !cur && <i className="needtag">нужно</i>}</span>
    {cur && !edit ? <div className="cpcur"><b>{cityBase(cur.name)}</b><button className="ghost mini" onClick={() => setEdit(true)}>Изменить</button></div>
      : <>
        <div className="chips">{top.map(c => <button key={c.id} className={c.id === value ? 'on' : ''} onClick={() => pick(c)}>{cityBase(c.name)}</button>)}</div>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Другой город — начните вводить" aria-label={label} />
        {!!hits.length && <div className="cplist">{hits.map(c => <button key={c.id} className="ghost" onClick={() => pick(c)}>{c.name}</button>)}</div>}
        {s && !hits.length && <p className="small muted">Такого города нет в списке Битрикса.</p>}
      </>}
  </div>
}

// «Жду ответа» (замечание Анны 06.11): клиент не ответил, но диалог не закончен. До выбранного дня не горит,
// в этот день сам всплывёт в «Сегодня»; в Битриксе — задача с датой.
const plusDays = n => { const d = new Date(); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10) }
export function WaitSheet({ path, title, onClose, onDone, api }) {
  const [next, setNext] = useState(plusDays(2))
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const opts = [[1, 'Завтра'], [2, 'Через 2 дня'], [3, 'Через 3 дня'], [7, 'Через неделю']]
  const send = () => { setBusy(true); api(`${path}/call`, { method: 'POST', body: { result: 'wait', next, text } })
    .then(r => onDone(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : `Ждём ответа до ${next.split('-').reverse().join('.')} — до этого дня не горит.`), e => { setErr(e.message); setBusy(false) }) }
  return <Sheet title={title || 'Жду ответа'} onClose={onClose}>
    <p className="small muted">Клиент не ответил или думает. До выбранного дня карточка не горит, в этот день сама поднимется в «Сегодня».</p>
    <div className="chips">{opts.map(([n, t]) => <button key={n} className={next === plusDays(n) ? 'on' : ''} onClick={() => setNext(plusDays(n))}>{t}</button>)}</div>
    <label>Или дата<input type="date" value={next} min={plusDays(1)} onChange={e => setNext(e.target.value)} /></label>
    <input value={text} onChange={e => setText(e.target.value)} placeholder="Чего ждём: «думает», «согласует с директором»" />
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
    <button disabled={!next || busy} onClick={send}>{busy ? 'Записываю…' : 'Ждать ответа'}</button>
  </Sheet>
}

// Статус смены / расхода значком (HEAD 09.11: «принято» ломалось по буквам — «может просто галочка»)
const MARK = { approved: ['✓', 'принято'], rejected: ['✕', 'отказ'], submitted: ['⏳', 'на проверке'], open: ['●', 'идёт'], cancelled: ['–', 'отменено'] }
export function StatusMark({ status }) {
  const [i, t] = MARK[status] || ['?', status]
  return <span className={'stmark st-' + status} title={t} aria-label={t}>{i}</span>
}

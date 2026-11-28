import React, { useEffect, useState } from 'react'
import { api, uuid } from './api.js'
import { Viewer, download, sendToGoogle } from './objects.jsx'

// «Отчёты таргета» (HEAD 26.11): агентство загружает свой отчёт — файл сам ложится на Диск в «04 ОТЧЁТЫ / Таргет / ГГГГ-ММ»;
// рядом приложение ставит цифры Meta и Битрикса за тот же период. HEAD — «Принято» или «Вернуть с вопросом».
const dm = s => s ? String(s).slice(0, 10).split('-').reverse().slice(0, 2).join('.') : ''
const num = (n, d = 0) => n == null ? '—' : Number(n).toLocaleString('ru-RU', { maximumFractionDigits: d })
const BADGE = { pending: 'warn', accepted: 'ok', returned: 'hot' }

function upload(file, onProgress) {
  return api('/mkt/adreports/uploads', { method: 'POST', body: { client_uid: uuid(), name: file.name, mime: file.type || 'application/octet-stream', size: file.size } })
    .then(r => r.done ? r.file : sendToGoogle(r.upload_url, file, onProgress)
      .then(g => api(`/mkt/adreports/uploads/${r.file_id}/done`, { method: 'POST', body: { drive_id: g.id } })))
}

function Form({ init, onClose, onSaved }) {
  const [b, setB] = useState(init?.id ? { ...init, rep_spend: init.rep_spend ?? '', rep_chats: init.rep_chats ?? '' }
    : { period_from: '', period_to: '', campaigns: '', note: '', files: [], rep_spend: '', rep_chats: '' })
  const [up, setUp] = useState(null)
  const [msg, setMsg] = useState('')
  const set = (k, v) => setB(s => ({ ...s, [k]: v }))
  const add = async list => {
    setMsg('')
    for (const file of list) {
      setUp(0)
      try { const f = await upload(file, setUp); setB(s => ({ ...s, files: [...s.files, f] })) } catch (e) { setMsg(`${file.name}: ${e.message}`) }
    }
    setUp(null)
  }
  const save = () => {
    if (up !== null) return setMsg('Дождись конца загрузки.')
    if (!b.files.length) return setMsg('Прикрепи файл отчёта.')
    if (!b.period_from || !b.period_to) return setMsg('Укажи период отчёта.')
    const body = { period_from: b.period_from, period_to: b.period_to, campaigns: b.campaigns || null, note: b.note || null, file_ids: b.files.map(f => f.id),
      rep_spend: b.rep_spend === '' ? null : +String(b.rep_spend).replace(',', '.'), rep_chats: b.rep_chats === '' ? null : +b.rep_chats }
    api(init?.id ? `/mkt/adreports/${init.id}` : '/mkt/adreports', { method: 'POST', body }).then(onSaved, e => setMsg(e.message))
  }
  return <div className="warnbox adrepform"><span className="kick">{init?.id ? 'Ответ на вопрос HEAD' : 'Новый отчёт'}</span>
    {init?.review_note && <p className="small why">HEAD: {init.review_note}</p>}
    {b.files.map(f => <div key={f.id} className="adrepfile"><span>📊</span><div><b>{f.name}</b><div className="small muted">загружено</div></div>
      <button className="ghost mini adrepdel" aria-label="Убрать" onClick={() => set('files', b.files.filter(x => x.id !== f.id))}>×</button></div>)}
    <label className={'photo mktup' + (up !== null ? ' busy' : '')}>{up !== null ? `Загрузка… ${Math.round(up * 100)}%` : b.files.length ? '+ Ещё файл' : '📎 Файл отчёта: Excel, PDF или скрин'}
      <input type="file" accept=".xlsx,.xls,.csv,.pdf,image/*" multiple hidden disabled={up !== null} onChange={e => { const fs = [...e.target.files]; e.target.value = ''; add(fs) }} /></label>
    <label className="muted small">Период</label>
    <div className="pair"><input type="date" aria-label="С" value={b.period_from} onChange={e => set('period_from', e.target.value)} />
      <input type="date" aria-label="По" value={b.period_to} onChange={e => set('period_to', e.target.value)} /></div>
    <input placeholder="Кампании: например, РК «Артгейм», РК «Картины»" value={b.campaigns} onChange={e => set('campaigns', e.target.value)} />
    <label className="muted small">Итог из отчёта — для сверки с кабинетом (по желанию)</label>
    <div className="pair"><input inputMode="decimal" placeholder="Потрачено, $" value={b.rep_spend} onChange={e => set('rep_spend', e.target.value)} />
      <input inputMode="numeric" placeholder="Переписок" value={b.rep_chats} onChange={e => set('rep_chats', e.target.value.replace(/\D/g, ''))} /></div>
    <textarea rows="3" placeholder="Вывод: что сработало, что отключаем, что дальше" value={b.note} onChange={e => set('note', e.target.value)} />
    {msg && <p className="small why">{msg}</p>}
    <div className="seg"><button className="ghost" onClick={onClose}>Отмена</button><button disabled={up !== null} onClick={save}>Отправить HEAD</button></div>
  </div>
}

function Card({ x, head, canUp, onChanged }) {
  const [d, setD] = useState(null)
  const [view, setView] = useState(null)
  const [ask, setAsk] = useState(null)
  const [edit, setEdit] = useState(false)
  const [msg, setMsg] = useState('')
  const load = () => api(`/mkt/adreports/${x.id}`).then(setD, e => setMsg(e.message))
  useEffect(() => { load() }, [x.id, x.status])
  const review = body => api(`/mkt/adreports/${x.id}/review`, { method: 'POST', body }).then(() => { setAsk(null); onChanged() }, e => setMsg(e.message))
  if (edit) return <Form init={x} onClose={() => setEdit(false)} onSaved={() => { setEdit(false); onChanged() }} />
  const c = d?.cmp, cur = c?.currency === 'USD' ? '$' : (c?.currency || '')
  const match = c && x.rep_spend != null && c.spend ? Math.abs(x.rep_spend - c.spend) / c.spend * 100 <= 3 : null
  const cpr = x.rep_spend && x.rep_chats ? x.rep_spend / x.rep_chats : c?.cpr
  return <div className="card adrep">
    <div className="head"><div><h3>{dm(x.period_from)}–{dm(x.period_to)}{x.campaigns ? ` · ${x.campaigns}` : ''}</h3>
      <div className="small muted">загрузил(а) {x.author} · {dm(x.created_at)}</div></div><span className={'badge ' + BADGE[x.status]}>{x.status_ru}</span></div>
    {x.files.map(f => <div key={f.id} className="adrepfile" role="button" onClick={() => setView(f)}><span>📊</span><div><b>{f.name}</b>
      <div className="small muted">открыть · <a onClick={e => { e.stopPropagation(); download(f) }}>скачать</a></div></div></div>)}
    {x.note && <p className="small">«{x.note}»</p>}
    {x.review_note && <p className="small why">HEAD: {x.review_note}</p>}
    {!d ? <p className="small muted">{msg || 'Считаю цифры Meta и Битрикса…'}</p> : <>
      <span className="kick">Сверка: отчёт · Meta · Битрикс</span>
      <div className="adrepcols">
        <div><span>Потрачено</span><b>{x.rep_spend != null ? `${num(x.rep_spend)} ${cur}` : '—'}</b><small>в отчёте</small></div>
        <div><span>Потрачено</span><b>{c.has_meta ? `${num(c.spend)} ${cur}` : '—'}</b><small className={match === true ? 'ok' : match === false ? 'why' : ''}>Meta{match === true ? ' · сходится' : match === false ? ' · не сходится' : ''}</small></div>
        <div><span>Переписки</span><b>{num(x.rep_chats ?? c.chats)}</b><small>{x.rep_chats != null ? `в отчёте · Meta ${num(c.chats)}` : 'Meta'}</small></div>
        <div><span>Цена переписки</span><b className={cpr && c.plan && cpr > c.plan ? 'why' : ''}>{cpr ? `${num(cpr, 2)} ${cur}` : '—'}</b><small>{c.plan ? `план ${c.plan} ${cur}` : 'плана нет'}</small></div>
        <div><span>Заявки</span><b>{c.bx_err ? '—' : num(c.bx.leads)}</b><small>Битрикс · таргет</small></div>
        <div><span>Сделки</span><b>{c.bx_err ? '—' : num(c.bx.deals)}</b><small>{c.bx.won ? `выиграно ${c.bx.won} · ${num(c.bx.won_sum / 1000)} тыс ₸` : 'выигранных нет'}</small></div>
      </div>
      {c.ads.length > 0 && <><p className="small muted">По объявлениям (Meta), дешевле — выше</p>
        {c.ads.map(a => <div key={a.ad_id} className="metatop"><span className={a.cpr && c.plan && a.cpr > c.plan * 1.5 ? 'why' : ''}>{a.ad_name || a.ad_id}</span>
          <b>{a.cpr ? `${num(a.cpr, 2)} ${cur}` : 'без переписок'} · {a.results}</b></div>)}</>}
      {d.verdict.length > 0 && <div className="warnbox"><b>Вывод</b>{d.verdict.map((v, i) => <p key={i} className="small">{v}</p>)}</div>}
    </>}
    {msg && d && <p className="small why">{msg}</p>}
    {head && x.status === 'pending' && (ask !== null
      ? <><textarea rows="2" placeholder="Вопрос агентству" value={ask} onChange={e => setAsk(e.target.value)} />
        <div className="seg"><button className="ghost" onClick={() => setAsk(null)}>Отмена</button><button disabled={!ask.trim()} onClick={() => review({ ok: false, note: ask })}>Отправить вопрос</button></div></>
      : <div className="seg"><button className="ghost" onClick={() => setAsk('')}>Вернуть с вопросом</button><button onClick={() => review({ ok: true })}>Принято</button></div>)}
    {canUp && x.status === 'returned' && <div className="seg"><button onClick={() => setEdit(true)}>Ответить и отправить снова</button></div>}
    {view && <Viewer f={view} onClose={() => setView(null)} />}
  </div>
}

export function AdReports() {
  const [d, setD] = useState(null)
  const [form, setForm] = useState(false)
  const [tick, setTick] = useState(0)
  useEffect(() => { api('/mkt/adreports').then(setD, e => setD({ err: e.message, items: [] })) }, [tick])
  if (!d) return <div className="card"><p className="muted">Загрузка…</p></div>
  const reload = () => setTick(t => t + 1)
  return <>
    <div className="card"><div className="head"><h3>Отчёты таргетолога</h3>{d.can_upload && !form && <button className="mini" onClick={() => setForm(true)}>+ Загрузить отчёт</button>}</div>
      <p className="small muted">Файл отчёта (Excel, PDF или скрин) ложится на Диск в «04 ОТЧЁТЫ / Таргет». Рядом приложение само ставит цифры Meta и заявки из Битрикса за тот же период.</p>
      {d.err && <p className="small why">{d.err}</p>}
      {form && <Form onClose={() => setForm(false)} onSaved={() => { setForm(false); reload() }} />}
      {!d.items.length && !form && <p className="small muted">Отчётов пока нет.</p>}
    </div>
    {d.items.map(x => <Card key={x.id + x.status} x={x} head={d.head} canUp={d.can_upload} onChanged={reload} />)}
  </>
}

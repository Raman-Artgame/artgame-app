import React, { useEffect, useState } from 'react'
import { api } from './api.js'

const money = n => n ? Math.round(n).toLocaleString('ru-RU') + ' ₸' : '—'
const dt = s => s ? new Date(s).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''
const strip = s => (s || '').replace(/<[^>]+>/g, '').replace(/\[\/?[A-Za-z]+\]/g, '')

// Карточка сделки в приложении: всё из Битрикса на одном экране. Битрикс — источник правды, здесь только показ и действия.
export function DealCard({ id, back, open }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const load = fresh => api(`/bx/deals/${id}/full${fresh ? '?fresh=1' : ''}`).then(setD, e => setErr(e.message))
  useEffect(() => { load(false) }, [id])
  if (err) return <div className="card"><a onClick={back}>← назад</a><p className="muted">{err}</p></div>
  if (!d) return <div className="card muted">Загружаю сделку № {id}…</div>
  const c = d.client || {}
  return <>
    <div className="card">
      <a onClick={back}>← к сделкам</a>
      <h2>№ {d.id} · {d.title.replace(new RegExp(`^№?\\s*${d.id}\\s*·?\\s*`), '')}</h2>
      <span className="tag">{d.stage_name}</span>{d.manager && <span className="tag">{d.manager}</span>}
      <div className="kv">
        <div><span className="muted small">Сумма</span><b>{money(d.sum)}</b></div>
        <div><span className="muted small">Площадь</span><b>{d.area ? d.area + ' м²' : '—'}</b></div>
        <div><span className="muted small">Услуга</span><b>{d.service || '—'}</b></div>
        <div><span className="muted small">Город</span><b>{d.city || '—'}</b></div>
      </div>
      {d.address && <p className="small">{d.address}</p>}
      <div className="dealbtns"><button className="ghost" onClick={() => open(d.id, 'kp')}>КП</button>
        <button className="ghost" onClick={() => open(d.id, 'docs')}>Документы</button>
        <button className="ghost" onClick={() => load(true)}>Обновить</button></div>
    </div>
    <div className="card"><h3>Клиент</h3>
      <div><b>{c.name || '—'}</b> <span className="muted small">{c.type}</span></div>
      {d.contact && d.contact !== c.name && <div className="small">{d.contact}</div>}
      {c.phone && <div><a href={`tel:${c.phone}`}>{c.phone}</a></div>}
      {c.email && <div className="small">{c.email}</div>}
      {d.comments && <p className="small muted">{strip(d.comments)}</p>}
    </div>
    <div className="card"><h3>Оплаты</h3>
      <div className="kv">
        <div><span className="muted small">Поступило</span><b>{money(d.pay.received)}</b></div>
        <div><span className="muted small">Долг</span><b>{money(d.pay.debt)}</b></div>
        {d.pay.next && <div><span className="muted small">Ближайший платёж</span><b>{d.pay.next.slice(0, 10)}</b></div>}
      </div>
      <p className="small muted">Считает сервер по поступлениям, отмечает HEAD.</p>
    </div>
    {!!d.files.length && <div className="card"><h3>Документы в сделке</h3>
      {d.files.map((f, i) => <div key={i} className="row"><span>{f.title}</span>{f.url ? <a href={f.url} target="_blank" rel="noreferrer">открыть</a> : <span className="muted small">в Битриксе</span>}</div>)}
    </div>}
    <div className="card"><h3>Лента</h3>
      {!d.feed.length && <p className="muted">Пока пусто.</p>}
      {d.feed.map((f, i) => <div key={i} className="row"><div><span className="muted small">{f.kind}{f.who ? ' · ' + f.who : ''}{f.done ? ' · сделано' : ''}</span><div>{strip(f.text).slice(0, 300)}</div></div><span className="muted small">{dt(f.at)}</span></div>)}
    </div>
    {!!d.history.length && <div className="card"><h3>Стадии</h3>
      {d.history.map((h, i) => <div key={i} className="row"><span>{h.stage}</span><span className="muted small">{dt(h.at)}</span></div>)}
    </div>}
  </>
}

// «Сегодня»: что требует действия. Сроки из «Значений» (mop.today.*).
export function Today({ openDeal }) {
  const [t, setT] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { api('/bx/today').then(setT, e => setErr(e.message)) }, [])
  if (err) return <div className="card"><h2>Сегодня</h2><p className="muted">{err}</p></div>
  if (!t) return <div className="card muted">Смотрю, что срочно…</div>
  const L = t.limits
  const block = (title, items, hint) => <div className="card"><h3>{title} <span className="muted small">{items.length}</span></h3>
    <p className="small muted">{hint}</p>
    {!items.length && <p className="muted small">Ничего.</p>}
    {items.map(d => <div key={d.id} className="row" onClick={() => openDeal(d.id)}><div><b>№ {d.id}</b> {d.title.replace(new RegExp(`^№?\\s*${d.id}\\s*·?\\s*`), '')}<div className="muted small">{d.stage_name}{d.sum ? ' · ' + money(d.sum) : ''}</div></div><a>открыть</a></div>)}
  </div>
  const total = t.new.length + t.kp.length + t.idle.length + t.tasks.length
  return <>
    <div className="card"><h2>Сегодня</h2><p className="muted">{total ? `Требуют действия: ${total}` : 'Всё в порядке, срочного нет.'}</p></div>
    {block('Новые заявки без ответа', t.new, `В «Взаимном информировании» дольше ${L.new_hours} ч.`)}
    {block('КП без ответа', t.kp, `После отправки КП прошло ${L.kp_days}+ дня.`)}
    {block('Сделки без движения', t.idle, `Нет изменений ${L.idle_days}+ дня (кроме «Отложено»).`)}
    <div className="card"><h3>Задачи в Битриксе <span className="muted small">{t.tasks.length}</span></h3>
      {!t.tasks.length && <p className="muted small">Открытых задач нет.</p>}
      {t.tasks.map(x => <div key={x.id} className="row" onClick={() => x.deal && openDeal(x.deal)}><div>{x.title}{x.deal && <div className="muted small">сделка № {x.deal}</div>}</div><span className="muted small">{x.deadline ? x.deadline.slice(0, 10) : ''}</span></div>)}
    </div>
  </>
}

import React, { useState } from 'react'
import { api } from './api.js'
import { cleanTitle, money } from './crm.jsx'
import { PaySheet, Payments } from './dealcard.jsx'

// «Оплаты» (HEAD 10.11): у кого в «Команде» стоит «Вносит оплаты клиентов» (Анна) — оплата клиента по любой сделке.
// Сделка по номеру или части названия → «Поступило» и «Долг» по журналу → «Внести оплату» с фото чека; HEAD сверяет в «Проверке».
// Оплата из поля сделки без даты (вносили в Битрикс до 10.11) — «Дата и чек»: заменяет поле, двойного счёта нет.
export function PayDesk() {
  const [q, setQ] = useState('')
  const [list, setList] = useState(null)
  const [d, setD] = useState(null)
  const [sheet, setSheet] = useState(null)   // {} — новая оплата, {slot} — «Дата и чек» к оплате из поля сделки без даты
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const open = id => { setErr(''); return api(`/pay/deals/${id}`).then(setD, e => setErr(e.message)) }
  const find = () => {
    const s = q.trim()
    if (!s) return
    setErr(''); setD(null); setList(null)
    api('/pay/deals?q=' + encodeURIComponent(s)).then(r => { setList(r); if (r.length === 1) open(r[0].id) }, e => setErr(e.message))
  }
  const done = t => { setSheet(null); setMsg(t); open(d.id); setTimeout(() => setMsg(''), 5000) }
  return <>
    <div className="card"><h2>Оплаты клиентов</h2>
      <p className="small muted">Найдите сделку по номеру или названию и внесите оплату с фото чека или выписки. HEAD сверит.</p>
      <div className="dealbar"><input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && find()}
        placeholder="№ сделки или название" enterKeyHint="search" /><button className="mini" disabled={!q.trim()} onClick={find}>Найти</button></div>
      {err && <p className="small why">{err}</p>}
      {list && !list.length && <p className="small muted">Не нашёл. Проверьте номер или напишите часть названия.</p>}
      {list?.length > 1 && list.map(x => <div key={x.id} className={'qrow' + (d?.id === x.id ? ' on' : '')} onClick={() => open(x.id)}>
        <div className="qmain"><b>№ {x.id} · {cleanTitle(x.title, x.id)}</b><div className="small muted">{[x.stage_name, x.manager, money(x.sum)].filter(Boolean).join(' · ')}</div></div>
        <span className="muted">›</span></div>)}
    </div>
    {msg && <div className="toast">{msg}</div>}
    {d && <div className="card"><h3>№ {d.id} · {cleanTitle(d.title, d.id)}</h3>
      <span className="tag">{d.stage_name}</span>{d.manager && <span className="tag">{d.manager}</span>}
      <div className="kv">
        <div><span className="muted small">Сумма</span><b>{money(d.sum)}</b></div>
        <div><span className="muted small">Поступило</span><b>{money(d.pay.received)}</b></div>
        <div><span className="muted small">{d.pay.lost ? 'Упущено' : 'Долг'}</span><b>{money(d.pay.lost || d.pay.debt)}</b></div>
        {d.pay.overpaid > 0 && <div><span className="muted small">Переплата</span><b>{money(d.pay.overpaid)}</b></div>}
      </div>
      {d.pay.on_check > 0 && <p className="small why">На сверке у HEAD: {money(d.pay.on_check)}.</p>}
      <Payments pay={d.pay} onDate={x => setSheet({ slot: x })} />
      <div className="dealbtns"><button className="mini" onClick={() => setSheet({})}>+ Внести оплату</button></div>
    </div>}
    {sheet && d && <PaySheet d={d} slot={sheet.slot} onClose={() => setSheet(null)} onDone={done} />}
  </>
}

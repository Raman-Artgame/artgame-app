import { Receipt } from './ui.jsx'
import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { enqueue, pending } from './queue.js'
import { shrink } from './work.jsx'
import { money } from './crm.jsx'

// Траты отдела продаж (HEAD 05.11): «Коммерческие расходы — отдел продаж». Чек обязателен, лимит МОП из «Значений»,
// сверх лимита — на одобрение HEAD. Привязка к сделке по желанию: в себестоимость не идёт, считается в стоимости привлечения.
const ST = { submitted: 'ждёт HEAD', approved: 'принято', rejected: 'отказ' }
const ICON = { sales_office: '📎', sales_trip: '🚕', sales_meet: '☕', sales_samples: '🎨' }

function Form({ cats, left, dealId, done, cancel }) {
  const [v, set] = useState({ category: cats[0]?.code, amount: '', paid_by: 'own', note: '', deal_id: dealId || '', receipt: '' })
  const [busy, setBusy] = useState(false)
  const over = left != null && +v.amount > left
  const send = async () => {
    setBusy(true)
    const n = await enqueue('/sales/expenses', { ...v, amount: +v.amount, deal_id: +v.deal_id || null, note: v.note || null })
    setBusy(false)
    done(n ? 'Сохранено на телефоне, отправится, когда будет сеть.' : over || left == null ? 'Трата ушла на одобрение HEAD.' : 'Трата записана.')
  }
  return <div className="dealedit">
    <div className="chips">{cats.map(c => <button key={c.code} className={v.category === c.code ? 'on' : ''} onClick={() => set({ ...v, category: c.code })}>{ICON[c.code]} {c.title}</button>)}</div>
    <input inputMode="numeric" value={v.amount} onChange={e => set({ ...v, amount: e.target.value.replace(/\D/g, '') })} placeholder="Сумма, ₸" />
    <div className="segf"><button className={v.paid_by === 'own' ? 'on' : ''} onClick={() => set({ ...v, paid_by: 'own' })}>Свои деньги</button>
      <button className={v.paid_by === 'company' ? 'on' : ''} onClick={() => set({ ...v, paid_by: 'company' })}>Деньги компании</button></div>
    <input value={v.note} onChange={e => set({ ...v, note: e.target.value })} placeholder="На что (например, такси на замер)" />
    {!dealId && <input inputMode="numeric" value={v.deal_id} onChange={e => set({ ...v, deal_id: e.target.value.replace(/\D/g, '') })} placeholder="№ сделки, если трата по ней (не обязательно)" />}
    {dealId && <p className="small muted">По сделке № {dealId}.</p>}
    <Receipt value={v.receipt} need pick={async f => set({ ...v, receipt: await shrink(f) })} />
    {+v.amount > 0 && <p className={'small ' + (over || left == null ? 'why' : 'muted')}>{left == null ? 'Лимит ещё не задан — трата уйдёт на одобрение HEAD.' : over ? `Сверх лимита (осталось ${money(left)}) — уйдёт на одобрение HEAD.` : `В пределах лимита, после неё останется ${money(left - v.amount)}.`}</p>}
    <div className="dealbtns"><button disabled={busy || !(+v.amount > 0) || !v.receipt} onClick={send}>Записать трату</button>
      <button className="ghost" onClick={cancel}>Отмена</button></div>
  </div>
}

export function SalesSpend({ dealId, won }) {
  const [m, setM] = useState(null)
  const [err, setErr] = useState('')
  const [form, setForm] = useState(false)
  const [msg, setMsg] = useState('')
  const load = () => api('/sales/expenses').then(setM, e => setErr(e.message))
  useEffect(() => { load(); const f = () => load(); window.addEventListener('artgame:queue', f); return () => window.removeEventListener('artgame:queue', f) }, [])
  if (err) return <div className="card"><h3>Траты отдела продаж</h3><p className="small muted">{err}</p></div>
  if (!m) return null
  const items = dealId ? m.items.filter(x => x.deal_id === dealId) : m.items
  const pct = m.limit ? Math.min(100, Math.round(m.spent / m.limit * 100)) : 0
  return <div className="card">
    <div className="head"><h3>{dealId ? 'Траты по сделке' : m.all ? 'Траты отдела продаж' : 'Мои траты'} <span className="muted small">{money(dealId ? items.reduce((a, x) => a + +x.amount, 0) : m.all ? m.total : m.spent)}</span></h3>
      {!form && <button className="mini" onClick={() => { setForm(true); setMsg('') }}>+ Трата</button>}</div>
    {!dealId && !m.all && <>{m.limit ? <><div className="bar"><i style={{ width: pct + '%' }} /></div>
      <p className="small muted">Лимит на месяц {money(m.limit)}, осталось <b>{money(m.left)}</b>. Сверх лимита трата ждёт HEAD.</p></>
      : <p className="small muted">Лимит на месяц ещё не задан: пока каждая трата ждёт одобрения HEAD.</p>}</>}
    {!dealId && m.all && <>
      <div className="kv">{m.categories.map(c => <div key={c.code}><span className="muted small">{ICON[c.code]} {c.title}</span><b>{money(m.by_category[c.code])}</b></div>)}</div>
      {won > 0 && m.total > 0 && <p className="small">Стоимость привлечения: <b>{money(m.total / won)}</b> на закрытую сделку ({won} в месяце).</p>}
      {(m.people || []).map(x => <div key={x.id} className="row"><span>{x.name}</span><b>{money(x.total)}</b></div>)}
      {m.waiting > 0 && <p className="small why">Ждут одобрения: {m.waiting} — во вкладке «Проверка».</p>}
    </>}
    {form && <Form cats={m.categories} left={m.all ? null : m.limit ? m.left : null} dealId={dealId} cancel={() => setForm(false)} done={t => { setForm(false); setMsg(t); load() }} />}
    {msg && <p className="small muted">{msg}</p>}
    {pending() > 0 && <p className="small muted">Ждут сети: {pending()}</p>}
    {items.slice(0, m.all ? 10 : 30).map(x => <div key={x.id} className="row">
      <div><b>{money(x.amount)}</b> {ICON[x.category]} {x.category_title}{m.all ? ' · ' + x.person : ''}
        <div className="small muted">{[new Date(x.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }), x.note, x.deal_id && !dealId ? `сделка № ${x.deal_id}` : '', x.paid_by === 'company' ? 'деньги компании' : x.payout_status === 'to_pay' ? 'к выплате' : x.payout_status === 'paid' ? 'выплачено' : ''].filter(Boolean).join(' · ')}
          {x.receipt_url && <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></>}</div>
        {x.reason && x.status === 'rejected' && <div className="small">Причина: {x.reason}</div>}</div>
      <span className={'tag st-' + x.status}>{ST[x.status] || x.status}</span>
    </div>)}
    {!items.length && !form && <p className="small muted">{dealId ? 'По этой сделке трат нет.' : 'В этом месяце трат нет.'}</p>}
  </div>
}

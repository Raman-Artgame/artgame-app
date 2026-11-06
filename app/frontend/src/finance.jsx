import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { enqueue, pending } from './queue.js'
import { shrink } from './work.jsx'
import { money } from './crm.jsx'

// Финансы (HEAD 06.11.2026): с ноября все деньги ведутся здесь, Google Таблица — витрина.
// Сводка месяца, журнал денег (счета Kaspi / наличные / переводы HEAD), ФОТ всех, кому платим, закупки из бюджета.
const ym = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
const shift = (m, k) => { const [y, mm] = m.split('-').map(Number); return ym(new Date(y, mm - 1 + k, 1)) }
const MONTH = m => new Date(m + '-01').toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
const today = () => new Date().toLocaleDateString('sv-SE')
const KIND = { income: 'Приход', opening: 'Остаток на начало', transfer: 'Перевод', fixed: 'Постоянные', variable: 'Переменные', tax: 'Налоги',
  project: 'На объект', stock: 'Склад', canvas: 'Мастерская холстов', sales: 'Отдел продаж' }
const ST = { submitted: 'ждёт HEAD', approved: 'принято', rejected: 'отказ' }
const err = set => e => set(e.message)

function MonthBar({ m, setM }) {
  return <div className="head"><button className="ghost mini" onClick={() => setM(shift(m, -1))}>‹</button>
    <b>{MONTH(m)}</b><button className="ghost mini" onClick={() => setM(shift(m, 1))}>›</button></div>
}

function Summary({ m }) {
  const [s, setS] = useState(null)
  const [e, setE] = useState('')
  const [exp, setExp] = useState('')
  useEffect(() => { setS(null); api('/fin/summary?ym=' + m).then(setS, err(setE)) }, [m])
  if (e) return <p className="small muted">{e}</p>
  if (!s) return <p className="small muted">Загрузка…</p>
  const c = s.costs
  const rows = [['На объекты (чеки)', c.project], ['Склад расходников', c.stock], ['Мастерская холстов', c.canvas], ['Отдел продаж', c.sales],
    ['ФОТ', c.payroll], ['Постоянные', c.fixed], ['Переменные', c.variable]]
  const sync = () => { setExp('Обновляю…'); api('/fin/export', { method: 'POST' }).then(r => setExp(r.ok ? 'Таблица обновлена.' : r.detail), err(setExp)) }
  return <>
    <div className="card"><h3>Прибыль месяца</h3>
      <div className="kv"><div><span className="muted small">Выручка с НДС</span><b>{money(s.revenue.gross)}</b></div>
        <div><span className="muted small">Без НДС</span><b>{money(s.revenue.net)}</b></div>
        <div><span className="muted small">Расходы</span><b>{money(Object.values(c).reduce((a, x) => a + x, 0))}</b></div>
        <div><span className="muted small">Прибыль</span><b>{money(s.profit)}</b></div>
        {s.ipn != null && <div><span className="muted small">ИПН (оценка)</span><b>{money(s.ipn)}</b></div>}</div>
      {rows.map(([t, v]) => <div key={t} className="row"><span>{t}</span><b>{money(v)}</b></div>)}
      <p className="small muted">Выручка — по дате конца работ (лист «Проекты»). ФОТ — начислено за месяц.</p></div>
    <div className="card"><h3>Деньги месяца</h3>
      <div className="kv"><div><span className="muted small">Пришло</span><b>{money(s.cash.in)}</b></div>
        <div><span className="muted small">Ушло</span><b>{money(s.cash.out)}</b></div></div>
      {s.cash.closing.map(b => <div key={b.code} className="row"><span>{b.title}</span>
        <span className="small muted">{money(+s.cash.opening.find(x => x.code === b.code)?.balance)} → <b>{money(+b.balance)}</b></span></div>)}
      {s.cash.company_paid_receipts > 0 && <p className="small muted">Чеки «деньги компании»: {money(s.cash.company_paid_receipts)} — внесите их списание со счёта в «Деньги».</p>}</div>
    {s.budget.length > 0 && <div className="card"><h3>Бюджет: план и факт</h3>
      {s.budget.map(b => <div key={b.code} className="row"><span>{b.title}<div className="small muted">{KIND[b.kind]}</div></span>
        <span className="small">{money(b.fact)} <span className="muted">/ {b.plan ? money(b.plan) : 'план не задан'}</span></span></div>)}</div>}
    {s.warn.map(w => <p key={w} className="small why">{w}</p>)}
    <div className="card"><button className="ghost" onClick={sync}>Обновить Google Таблицу</button>{exp && <p className="small muted">{exp}</p>}</div>
  </>
}

function LedgerForm({ d, done, cancel }) {
  const [v, set] = useState({ op_date: today(), account: d.accounts[0]?.code, article: 'client_payment', amount: '', to_account: '', deal_id: '', note: '', period: '', receipt: '' })
  const [busy, setBusy] = useState(false)
  const [e, setE] = useState('')
  const arts = d.articles.filter(a => a.kind !== 'payroll')
  const kind = arts.find(a => a.code === v.article)?.kind
  const send = () => {
    setBusy(true); setE('')
    api('/fin/ledger', { method: 'POST', body: { client_uid: crypto.randomUUID(), op_date: v.op_date, account: v.account, article: v.article, amount: +v.amount,
      to_account: kind === 'transfer' ? v.to_account : null, deal_id: +v.deal_id || null, note: v.note || null, period: v.period || null, receipt: v.receipt || null } })
      .then(done, err(setE)).finally(() => setBusy(false))
  }
  return <div className="dealedit">
    <select value={v.article} onChange={e => set({ ...v, article: e.target.value })}>
      {Object.entries(KIND).filter(([k]) => arts.some(a => a.kind === k)).map(([k, t]) => <optgroup key={k} label={t}>
        {arts.filter(a => a.kind === k).map(a => <option key={a.code} value={a.code}>{a.title}</option>)}</optgroup>)}</select>
    <input inputMode="numeric" value={v.amount} onChange={e => set({ ...v, amount: e.target.value.replace(/\D/g, '') })} placeholder="Сумма, ₸" />
    <div className="segf">{d.accounts.map(a => <button key={a.code} className={v.account === a.code ? 'on' : ''} onClick={() => set({ ...v, account: a.code })}>{a.title}</button>)}</div>
    {kind === 'transfer' && <select value={v.to_account} onChange={e => set({ ...v, to_account: e.target.value })}>
      <option value="">Куда перевести…</option>{d.accounts.filter(a => a.code !== v.account).map(a => <option key={a.code} value={a.code}>{a.title}</option>)}</select>}
    <input type="date" value={v.op_date} onChange={e => set({ ...v, op_date: e.target.value })} />
    {['fixed', 'variable', 'tax'].includes(kind) && <input type="month" value={v.period} onChange={e => set({ ...v, period: e.target.value })} title="За какой месяц (если не месяц даты)" />}
    {kind === 'income' && <input inputMode="numeric" value={v.deal_id} onChange={e => set({ ...v, deal_id: e.target.value.replace(/\D/g, '') })} placeholder="№ сделки в Битриксе" />}
    <input value={v.note} onChange={e => set({ ...v, note: e.target.value })} placeholder="Комментарий" />
    <label className="photo">{v.receipt ? <img src={v.receipt} alt="чек" /> : <span>📷 Чек / квитанция (по желанию)</span>}
      <input type="file" accept="image/*" hidden onChange={async e => e.target.files[0] && set({ ...v, receipt: await shrink(e.target.files[0]) })} /></label>
    {e && <p className="small why">{e}</p>}
    <div className="dealbtns"><button disabled={busy || !(+v.amount > 0) || (kind === 'transfer' && !v.to_account)} onClick={send}>Записать</button>
      <button className="ghost" onClick={cancel}>Отмена</button></div>
  </div>
}

function Ledger({ m, d }) {
  const [rows, setRows] = useState(null)
  const [form, setForm] = useState(false)
  const [e, setE] = useState('')
  const load = () => api('/fin/ledger?ym=' + m).then(setRows, err(setE))
  useEffect(() => { setRows(null); load() }, [m])
  const cancel = id => confirm('Отменить операцию? Она останется в журнале зачёркнутой.') && api(`/fin/ledger/${id}/cancel`, { method: 'POST' }).then(load, err(setE))
  return <div className="card">
    <div className="head"><h3>Движение денег</h3>{!form && <button className="mini" onClick={() => setForm(true)}>+ Операция</button>}</div>
    {form && <LedgerForm d={d} cancel={() => setForm(false)} done={() => { setForm(false); load() }} />}
    {e && <p className="small why">{e}</p>}
    {rows?.map(x => <div key={x.id} className="row" style={x.status === 'cancelled' ? { opacity: .45, textDecoration: 'line-through' } : null}>
      <div><b>{x.direction === 'in' ? '+' : '−'}{money(+x.amount)}</b> {x.article_title}
        <div className="small muted">{[new Date(x.op_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }), x.account_title, x.payee_name,
          x.deal_id && `сделка № ${x.deal_id}`, x.period !== m && `за ${x.period}`, x.note].filter(Boolean).join(' · ')}
          {x.receipt_url && <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></>}</div></div>
      {x.status === 'active' && <button className="ghost mini" onClick={() => cancel(x.id)}>✕</button>}
    </div>)}
    {rows && !rows.length && !form && <p className="small muted">Операций за месяц нет. Начните с «Остаток на начало» по каждому счёту.</p>}
  </div>
}

function PayRow({ r, m, d, reload }) {
  const [open, setOpen] = useState(false)
  const [v, set] = useState({ amount: '', account: d.accounts[0]?.code, op_date: today(), adj: '', detail: '' })
  const [e, setE] = useState('')
  const pay = () => api(`/fin/payroll/${m}/pay`, { method: 'POST', body: { client_uid: crypto.randomUUID(), payee_id: r.id, amount: +v.amount, account: v.account, op_date: v.op_date } })
    .then(() => { setOpen(false); reload() }, err(setE))
  const adj = () => api(`/fin/payroll/${m}/accrual`, { method: 'POST', body: { payee_id: r.id, amount: +v.adj, detail: v.detail } }).then(reload, err(setE))
  const drop = id => api(`/fin/accruals/${id}/cancel`, { method: 'POST' }).then(reload, err(setE))
  return <div className="row" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
    <div className="head" onClick={() => setOpen(!open)} style={{ cursor: 'pointer' }}>
      <span>{r.name} <span className="small muted">{r.group}{r.pay_rule === 'weekly' ? ' · еженедельно' : ''}</span></span>
      <span className="small">{money(r.accrued)} · <span className={r.left > 0 ? 'why' : 'muted'}>{r.left > 0 ? 'осталось ' + money(r.left) : r.accrued ? 'выплачено' : '—'}</span></span></div>
    {open && <div className="dealedit">
      {r.lines.map(a => <div key={a.id} className="small row"><span>{a.detail || a.kind}</span>
        <span>{money(+a.amount)} {a.kind === 'manual' && <a onClick={() => drop(a.id)}>убрать</a>}</span></div>)}
      <p className="small muted">Выплачено {money(r.paid)}{r.last_paid ? ', последняя ' + new Date(r.last_paid).toLocaleDateString('ru-RU') : ''}.</p>
      <input inputMode="numeric" value={v.amount} onChange={e => set({ ...v, amount: e.target.value.replace(/\D/g, '') })} placeholder={`Выплата, ₸ (осталось ${Math.max(0, Math.round(r.left))})`} />
      <div className="segf">{d.accounts.map(a => <button key={a.code} className={v.account === a.code ? 'on' : ''} onClick={() => set({ ...v, account: a.code })}>{a.title}</button>)}</div>
      <input type="date" value={v.op_date} onChange={e => set({ ...v, op_date: e.target.value })} />
      <button disabled={!(+v.amount > 0)} onClick={pay}>Отметить выплату</button>
      <input value={v.adj} onChange={e => set({ ...v, adj: e.target.value.replace(/[^\d-]/g, '') })} placeholder="Доплата / удержание, ₸ (минус — удержание)" />
      <input value={v.detail} onChange={e => set({ ...v, detail: e.target.value })} placeholder="За что" />
      <button className="ghost" disabled={!+v.adj || v.detail.trim().length < 2} onClick={adj}>Добавить начисление</button>
      {e && <p className="small why">{e}</p>}
    </div>}
  </div>
}

function Payroll({ m, d }) {
  const [p, setP] = useState(null)
  const [e, setE] = useState('')
  const [busy, setBusy] = useState(false)
  const load = () => api('/fin/payroll/' + m).then(setP, err(setE))
  useEffect(() => { setP(null); load() }, [m])
  const compute = () => { setBusy(true); setE(''); api(`/fin/payroll/${m}/compute`, { method: 'POST' }).then(r => { setP(r); setE((r.warn || []).join('; ')) }, err(setE)).finally(() => setBusy(false)) }
  return <div className="card">
    <div className="head"><h3>ФОТ</h3><button className="mini" disabled={busy} onClick={compute}>{busy ? 'Считаю…' : 'Пересчитать'}</button></div>
    {p && <div className="kv"><div><span className="muted small">Начислено</span><b>{money(p.accrued)}</b></div>
      <div><span className="muted small">Выплачено</span><b>{money(p.paid)}</b></div><div><span className="muted small">Осталось</span><b>{money(p.left)}</b></div></div>}
    <p className="small muted">Пересчёт берёт смены, бонусы печати, оклады, % МОП и возмещение чеков «свои деньги». Ручные начисления не трогает.</p>
    {e && <p className="small why">{e}</p>}
    {p?.rows.map(r => <PayRow key={r.id} r={r} m={m} d={d} reload={load} />)}
  </div>
}

const SCHEME = { shifts: 'смены × ставка', salary: 'оклад', mop: 'оклад + % МОП', manual: 'вручную' }
function Payees({ d }) {
  const [rows, setRows] = useState(null)
  const [v, set] = useState(null)
  const [e, setE] = useState('')
  const load = () => api('/fin/payees').then(setRows, err(setE))
  useEffect(() => { load() }, [])
  const save = () => api(v.id ? `/fin/payees/${v.id}` : '/fin/payees', { method: 'POST',
    body: { name: v.name, grp: v.grp, scheme: v.scheme, amount: v.amount === '' || v.amount == null ? null : +v.amount, amount_key: v.amount_key || null, pay_rule: v.pay_rule, note: v.note || null, status: v.status } })
    .then(() => { set(null); load() }, err(setE))
  return <div className="card">
    <div className="head"><h3>Кому платим</h3>{!v && <button className="mini" onClick={() => set({ name: '', grp: 'office', scheme: 'salary', amount: '', amount_key: '', pay_rule: 'month', note: '', status: 'active' })}>+ Получатель</button>}</div>
    <p className="small muted">Команда из приложения добавляется сама. Сюда — бухгалтер, SMM, подрядчики и все, кого нет в приложении.</p>
    {v && <div className="dealedit">
      <input value={v.name} onChange={e => set({ ...v, name: e.target.value })} placeholder="Имя или компания" disabled={!!v.person_id} />
      <select value={v.grp} onChange={e => set({ ...v, grp: e.target.value })}>{Object.entries(d.groups).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select>
      <select value={v.scheme} onChange={e => set({ ...v, scheme: e.target.value })}>{Object.entries(SCHEME).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select>
      {v.scheme === 'salary' && <><input inputMode="numeric" value={v.amount ?? ''} onChange={e => set({ ...v, amount: e.target.value.replace(/\D/g, '') })} placeholder="Оклад в месяц, ₸" />
        <input value={v.amount_key || ''} onChange={e => set({ ...v, amount_key: e.target.value })} placeholder="или ключ в «Значениях» (pay.accountant.month)" /></>}
      <div className="segf"><button className={v.pay_rule === 'month' ? 'on' : ''} onClick={() => set({ ...v, pay_rule: 'month' })}>Аванс + расчёт</button>
        <button className={v.pay_rule === 'weekly' ? 'on' : ''} onClick={() => set({ ...v, pay_rule: 'weekly' })}>Еженедельно</button></div>
      <input value={v.note || ''} onChange={e => set({ ...v, note: e.target.value })} placeholder="Заметка" />
      {e && <p className="small why">{e}</p>}
      <div className="dealbtns"><button disabled={v.name.trim().length < 2} onClick={save}>Сохранить</button>
        {v.id && <button className="ghost" onClick={() => { set({ ...v, status: v.status === 'active' ? 'archived' : 'active' }) }}>{v.status === 'active' ? 'В архив' : 'Вернуть'}</button>}
        <button className="ghost" onClick={() => set(null)}>Отмена</button></div></div>}
    {rows?.map(x => <div key={x.id} className="row" onClick={() => set({ ...x, amount: x.amount ?? '' })} style={{ cursor: 'pointer', opacity: x.status === 'active' ? 1 : .5 }}>
      <span>{x.name}<div className="small muted">{d.groups[x.grp]} · {SCHEME[x.scheme]}{x.amount ? ' ' + money(+x.amount) : x.amount_key ? ' · ' + x.amount_key : ''}</div></span>
      <span className="small muted">{x.person_id ? 'в приложении' : ''}</span></div>)}
  </div>
}

export function Finance() {
  const [m, setM] = useState(ym())
  const [t, setT] = useState('sum')
  const [d, setD] = useState(null)
  const [e, setE] = useState('')
  useEffect(() => { api('/fin/dict').then(setD, err(setE)) }, [])
  if (e) return <div className="card"><p className="muted">{e}</p></div>
  if (!d) return <div className="card muted">Загрузка…</div>
  return <>
    <div className="card"><MonthBar m={m} setM={setM} />
      <div className="segf">{[['sum', 'Сводка'], ['cash', 'Деньги'], ['pay', 'ФОТ'], ['buy', 'Закупки'], ['who', 'Люди']].map(([k, n]) =>
        <button key={k} className={t === k ? 'on' : ''} onClick={() => setT(k)}>{n}</button>)}</div></div>
    {t === 'sum' ? <Summary m={m} /> : t === 'cash' ? <Ledger m={m} d={d} /> : t === 'pay' ? <Payroll m={m} d={d} /> : t === 'buy' ? <StockSpend /> : <Payees d={d} />}
  </>
}

// ---------- закупки из бюджета: склад расходников и мастерская холстов ----------

function StockForm({ cats, limits, done, cancel }) {
  const [v, set] = useState({ category: cats[0]?.code, amount: '', paid_by: 'own', note: '', deal_id: '', receipt: '' })
  const [busy, setBusy] = useState(false)
  const art = cats.find(c => c.code === v.category)?.article
  const l = limits[art] || {}
  const left = l.left
  const over = left != null && +v.amount > left
  const send = async () => {
    setBusy(true)
    const n = await enqueue('/stock/expenses', { ...v, amount: +v.amount, deal_id: +v.deal_id || null, note: v.note || null })
    setBusy(false)
    done(n ? 'Сохранено на телефоне, отправится, когда будет сеть.' : over || left == null ? 'Закупка ушла на одобрение HEAD.' : 'Закупка записана.')
  }
  return <div className="dealedit">
    <div className="chips">{cats.map(c => <button key={c.code} className={v.category === c.code ? 'on' : ''} onClick={() => set({ ...v, category: c.code })}>{c.title}</button>)}</div>
    <input inputMode="numeric" value={v.amount} onChange={e => set({ ...v, amount: e.target.value.replace(/\D/g, '') })} placeholder="Сумма, ₸" />
    <div className="segf"><button className={v.paid_by === 'own' ? 'on' : ''} onClick={() => set({ ...v, paid_by: 'own' })}>Свои деньги</button>
      <button className={v.paid_by === 'company' ? 'on' : ''} onClick={() => set({ ...v, paid_by: 'company' })}>Деньги компании</button></div>
    <input value={v.note} onChange={e => set({ ...v, note: e.target.value })} placeholder="Что купил (например, 10 л белой краски)" />
    {art === 'canvas' && <input inputMode="numeric" value={v.deal_id} onChange={e => set({ ...v, deal_id: e.target.value.replace(/\D/g, '') })} placeholder="№ сделки, если холсты под заказ (не обязательно)" />}
    <label className="photo">{v.receipt ? <img src={v.receipt} alt="чек" /> : <span>📷 Фото чека (обязательно)</span>}
      <input type="file" accept="image/*" capture="environment" hidden onChange={async e => e.target.files[0] && set({ ...v, receipt: await shrink(e.target.files[0]) })} /></label>
    {+v.amount > 0 && <p className={'small ' + (over || left == null ? 'why' : 'muted')}>{left == null ? 'Лимит ещё не задан — закупка уйдёт на одобрение HEAD.' : over ? `Сверх лимита (осталось ${money(left)}) — уйдёт на одобрение HEAD.` : `В пределах лимита, после неё останется ${money(left - v.amount)}.`}</p>}
    <div className="dealbtns"><button disabled={busy || !(+v.amount > 0) || !v.receipt} onClick={send}>Записать закупку</button>
      <button className="ghost" onClick={cancel}>Отмена</button></div>
  </div>
}

export function StockSpend() {
  const [m, setM] = useState(null)
  const [e, setE] = useState('')
  const [form, setForm] = useState(false)
  const [msg, setMsg] = useState('')
  const load = () => api('/stock/expenses').then(setM, err(setE))
  useEffect(() => { load(); const f = () => load(); window.addEventListener('artgame:queue', f); return () => window.removeEventListener('artgame:queue', f) }, [])
  if (e) return <div className="card"><h3>Закупки</h3><p className="small muted">{e}</p></div>
  if (!m) return null
  const title = Object.values(m.limits).map(l => l.title).join(' и ')
  return <div className="card">
    <div className="head"><h3>{m.all ? 'Закупки из бюджета' : title} <span className="muted small">{money(m.total)}</span></h3>
      {!form && <button className="mini" onClick={() => { setForm(true); setMsg('') }}>+ Закупка</button>}</div>
    <p className="small muted">Закупки впрок, не на конкретный объект. Идут в расходы бюджета, не в себестоимость объекта.</p>
    {!m.all && Object.entries(m.limits).map(([k, l]) => <div key={k}>{l.limit ? <>
      <div className="bar"><i style={{ width: Math.min(100, Math.round(l.spent / l.limit * 100)) + '%' }} /></div>
      <p className="small muted">{l.title}: лимит на месяц {money(l.limit)}, осталось <b>{money(l.left)}</b>. Сверх лимита — ждёт HEAD.</p></>
      : <p className="small muted">{l.title}: лимит ещё не задан, каждая закупка ждёт одобрения HEAD.</p>}</div>)}
    {m.waiting > 0 && m.all && <p className="small why">Ждут одобрения: {m.waiting} — во вкладке «Проверка».</p>}
    {form && <StockForm cats={m.categories} limits={m.all ? {} : m.limits} cancel={() => setForm(false)} done={t => { setForm(false); setMsg(t); load() }} />}
    {msg && <p className="small muted">{msg}</p>}
    {pending() > 0 && <p className="small muted">Ждут сети: {pending()}</p>}
    {m.items.map(x => <div key={x.id} className="row">
      <div><b>{money(+x.amount)}</b> {x.category_title}{m.all ? ' · ' + x.person : ''}
        <div className="small muted">{[new Date(x.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }), x.note, x.deal_id && `сделка № ${x.deal_id}`,
          x.paid_by === 'company' ? 'деньги компании' : x.payout_status === 'to_pay' ? 'к выплате' : x.payout_status === 'paid' ? 'выплачено' : ''].filter(Boolean).join(' · ')}
          {x.receipt_url && <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></>}</div>
        {x.reason && x.status === 'rejected' && <div className="small">Причина: {x.reason}</div>}</div>
      <span className={'tag st-' + x.status}>{ST[x.status] || x.status}</span>
    </div>)}
    {!m.items.length && !form && <p className="small muted">В этом месяце закупок нет.</p>}
  </div>
}

// ---------- мои выплаты: каждый видит только своё ----------

const LINE = { piece: 'Смены', bonus: 'Бонус', topup: 'Доплата до минимума', salary: 'Оклад', mop_pct: '% от выручки', mop_bonus: 'Бонус за план',
  reimburse: 'Возмещение чеков', manual: 'Начисление HEAD' }
export function MyPay() {
  const [m, setM] = useState(ym())
  const [p, setP] = useState(null)
  useEffect(() => { setP(null); api('/fin/my?ym=' + m).then(setP, () => setP({ lines: [], accrued: 0, paid: 0, left: 0 })) }, [m])
  return <div className="card"><h3>Мои выплаты</h3><MonthBar m={m} setM={setM} />
    {p && <><div className="kv"><div><span className="muted small">Начислено</span><b>{money(p.accrued)}</b></div>
      <div><span className="muted small">Выплачено</span><b>{money(p.paid)}</b></div><div><span className="muted small">Осталось</span><b>{money(p.left)}</b></div></div>
      {p.lines.map((a, i) => <div key={i} className="row small"><span>{a.detail || LINE[a.kind]}</span><b>{money(+a.amount)}</b></div>)}
      {!p.lines.length && <p className="small muted">За этот месяц начислений пока нет — HEAD считает ФОТ в конце месяца.</p>}</>}
  </div>
}

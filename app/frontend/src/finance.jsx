import { Receipt } from './ui.jsx'
import React, { useEffect, useState } from 'react'
import { api, uuid } from './api.js'
import { enqueue, pending } from './queue.js'
import { shrink } from './work.jsx'
import { money } from './crm.jsx'
import { Donut, HBars, MonthBars, mln } from './charts.jsx'

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
    ...(c.materials ? [['Материалы и транспорт (оценка старой таблицы)', c.materials]] : []),
    ['ФОТ', c.payroll], ['Постоянные', c.fixed], ['Переменные', c.variable]]
  const sync = () => { setExp('Обновляю…'); api('/fin/export', { method: 'POST' }).then(r => setExp(r.ok ? 'Таблица обновлена.' : r.detail), err(setExp)) }
  return <>
    <div className="card"><h3>Прибыль месяца</h3>
      <div className="kv"><div><span className="muted small">Выручка с НДС</span><b>{money(s.revenue.gross)}</b></div>
        <div><span className="muted small">Без НДС</span><b>{money(s.revenue.net)}</b></div>
        <div><span className="muted small">Расходы</span><b>{money(Object.values(c).reduce((a, x) => a + x, 0))}</b></div>
        <div><span className="muted small">Прибыль до ИПН</span><b>{money(s.profit)}</b></div>
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
        <span className="small">{money(b.fact)}{b.estimate ? ' (оценка)' : ''} <span className="muted">/ {b.plan ? money(b.plan) : 'план не задан'}</span></span></div>)}</div>}
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
    api('/fin/ledger', { method: 'POST', body: { client_uid: uuid(), op_date: v.op_date, account: v.account, article: v.article, amount: +v.amount,
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

// оплата клиента, которую внёс МОП в сделке (HEAD 10.11), и HEAD её ещё не сверил
const unchecked = x => x.source === 'app' && x.status === 'active' && !x.checked_at && ['client_payment', 'design_prepay'].includes(x.article_code)

// График постоянных оплат (HEAD 12.11): в день оплаты — «Оплатить сегодня» здесь, на Пульте и в боте.
// Аренды и счета — переводом с чеком (обязателен) или наличными; подписки — автосписание, пишутся сами.
const RST = { overdue: ['просрочено', 'why'], today: ['сегодня', 'why'], soon: ['скоро', ''], later: ['', ''], paid: ['оплачено', 'ok'], off: ['в архиве', ''] }
const MON = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря']
const dm = s => s ? new Date(s + 'T12:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' }) : ''
const when = x => x.every === 'year' ? 'раз в год' : 'каждый месяц'
const ORD = { overdue: 0, today: 1, soon: 2, later: 3, paid: 4, off: 5 }
const bySoon = (a, b) => ORD[a.status] - ORD[b.status] || (a.due || '').localeCompare(b.due || '')
export function Bills({ d, onPaid }) {
  const [r, setR] = useState(null)
  const [e, setE] = useState('')
  const [pay, setPay] = useState(null)    // {id, amount, cash, receipt}
  const [edit, setEdit] = useState(null)
  const [busy, setBusy] = useState(false)
  const bank = d.accounts.filter(a => a.code !== 'cash')
  const hasCash = d.accounts.some(a => a.code === 'cash')
  const [acc, setAcc] = useState((bank[0] || d.accounts[0])?.code)
  const load = () => api('/fin/recurring').then(setR, err(setE))
  useEffect(() => { load() }, [])
  const send = x => {
    setBusy(true); setE('')
    api(`/fin/recurring/${x.id}/pay`, { method: 'POST', body: { client_uid: uuid(), cycle: x.cycle, account: pay.cash ? 'cash' : acc, op_date: today(),
      amount: +pay.amount, receipt: pay.receipt || null } })
      .then(() => { setPay(null); load(); onPaid && onPaid() }, err(setE)).finally(() => setBusy(false))
  }
  const save = () => api(edit.id ? `/fin/recurring/${edit.id}` : '/fin/recurring', { method: 'POST',
    body: { title: edit.title, article: edit.article, every: edit.every, day: +edit.day, month: edit.every === 'year' ? +edit.month : null,
      auto: edit.auto, account: edit.account || 'kaspi', active: edit.active } }).then(() => { setEdit(null); load() }, err(setE))
  if (!r) return <div className="card"><h3>Постоянные оплаты</h3><p className="small muted">{e || 'Загрузка…'}</p></div>
  const open = x => pay?.id === x.id
  const row = x => {
    const [st, cls] = RST[x.status] || ['', '']
    const can = ['overdue', 'today', 'soon'].includes(x.status)
    return <div key={x.id} className="row bill" style={x.active ? null : { opacity: .5 }}>
      <div className="billmain" onClick={() => setEdit({ ...x, month: x.month || 1 })} role="button">
        <b>{x.title}</b> · {x.amount ? <span className="nowrap">{money(x.amount)}</span> : <span className="muted">сумма при оплате</span>}
        <div className="small muted">{x.status === 'paid' && x.last_paid ? <><span className="ok">{x.auto ? 'списано' : 'оплачено'} {dm(x.last_paid.date)}</span> · дальше {dm(x.due)}</>
          : <>{dm(x.due)}{st && <> · <span className={cls}>{st}</span></>}</>} · {when(x)}</div></div>
      {can && !open(x) && <button className={'mini' + (['overdue', 'today'].includes(x.status) ? '' : ' ghost')}
        onClick={() => setPay({ id: x.id, amount: x.amount ? String(x.amount) : '', cash: false, receipt: '' })}>Оплачено</button>}
      {open(x) && <div className="dealedit" style={{ flexBasis: '100%' }}>
        <input inputMode="numeric" value={pay.amount} onChange={v => setPay({ ...pay, amount: v.target.value.replace(/\D/g, '') })} placeholder="Сумма, ₸" />
        <div className="seg"><button className={pay.cash ? 'ghost' : ''} onClick={() => setPay({ ...pay, cash: false })}>Переводом</button>
          {hasCash && <button className={pay.cash ? '' : 'ghost'} onClick={() => setPay({ ...pay, cash: true })}>Наличными</button>}</div>
        {!pay.cash && bank.length > 1 && <select value={acc} onChange={v => setAcc(v.target.value)}>{bank.map(a => <option key={a.code} value={a.code}>Со счёта: {a.title}</option>)}</select>}
        <Receipt value={pay.receipt} pick={async f => setPay({ ...pay, receipt: await shrink(f) })} />
        <p className="small muted">{pay.cash ? 'Наличными — чек по желанию.' : x.auto ? 'Автосписание — чек по желанию.' : 'Переводом — приложите чек, без него не сохранится.'}</p>
        <div className="seg"><button disabled={busy || !(+pay.amount > 0) || (!pay.cash && !x.auto && !pay.receipt)} onClick={() => send(x)}>
          Оплачено {+pay.amount > 0 ? money(+pay.amount) : ''}</button><button className="ghost" onClick={() => setPay(null)}>Отмена</button></div></div>}
    </div>
  }
  const manual = r.items.filter(x => !x.auto && x.active).sort(bySoon), auto = r.items.filter(x => x.auto && x.active).sort(bySoon), off = r.items.filter(x => !x.active)
  return <div className="card">
    <div className="head"><h3>Постоянные оплаты</h3><b className="nowrap">{money(r.month_total)}<span className="small muted"> /мес</span></b></div>
    {r.due.length > 0 ? <p className="small why">Оплатить сейчас: {r.due.length} на {money(r.due_total)}</p>
      : <p className="small muted">Сегодня оплачивать нечего. В день оплаты напомню здесь, на Пульте и в боте.</p>}
    {e && <p className="small why">{e}</p>}
    {edit && <div className="dealedit">
      <input value={edit.title} onChange={v => setEdit({ ...edit, title: v.target.value })} placeholder="Что оплачиваем" />
      <select value={edit.article} onChange={v => setEdit({ ...edit, article: v.target.value })}>
        <option value="">Статья расходов…</option>{r.articles.map(a => <option key={a.code} value={a.code}>{a.title}</option>)}</select>
      <div className="segf"><button className={edit.every === 'month' ? 'on' : ''} onClick={() => setEdit({ ...edit, every: 'month' })}>Каждый месяц</button>
        <button className={edit.every === 'year' ? 'on' : ''} onClick={() => setEdit({ ...edit, every: 'year' })}>Раз в год</button></div>
      <div className="seg"><input inputMode="numeric" value={edit.day} onChange={v => setEdit({ ...edit, day: v.target.value.replace(/\D/g, '').slice(0, 2) })} placeholder="Число" />
        {edit.every === 'year' && <select value={edit.month} onChange={v => setEdit({ ...edit, month: +v.target.value })}>{MON.map((n, i) => <option key={i} value={i + 1}>{n}</option>)}</select>}</div>
      <div className="segf"><button className={edit.auto ? '' : 'on'} onClick={() => setEdit({ ...edit, auto: false })}>Плачу сам</button>
        <button className={edit.auto ? 'on' : ''} onClick={() => setEdit({ ...edit, auto: true })}>Автосписание</button></div>
      <p className="small muted">Сумма — из «Значений» по статье, здесь её не меняем. Нет суммы в «Значениях» — вводите при оплате.</p>
      <div className="dealbtns"><button disabled={edit.title.trim().length < 2 || !edit.article || !(+edit.day >= 1 && +edit.day <= 31)} onClick={save}>Сохранить</button>
        {edit.id && <button className="ghost" onClick={() => setEdit({ ...edit, active: !edit.active })}>{edit.active ? 'В архив' : 'Вернуть'}</button>}
        <button className="ghost" onClick={() => setEdit(null)}>Отмена</button></div></div>}
    {manual.map(row)}
    {auto.length > 0 && <><p className="small muted sub">Автосписание: записывается само в день списания, в бот — «Списано». Не та сумма — отмените строку ниже в «Движении денег», платёж снова появится здесь.</p>{auto.map(row)}</>}
    {!edit && <button className="ghost" onClick={() => setEdit({ title: '', article: '', every: 'month', day: '', month: 1, auto: false, account: 'kaspi', active: true })}>+ Постоянная оплата</button>}
    {off.length > 0 && <details className="paidlog"><summary className="small">В архиве: {off.length}</summary>{off.map(row)}</details>}
    {r.paid.length > 0 && <details className="paidlog"><summary className="small">Оплачено за 60 дней: {r.paid.length}</summary>
      {r.paid.map(x => <div key={x.id} className="row"><div><b>{x.title}</b> · {money(+x.amount)}
        <div className="small muted">{dm(x.op_date)} · {x.account}{x.auto ? ' · автосписание' : x.receipt_url ? <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></> : ' · без чека'}</div></div></div>)}</details>}
  </div>
}

function Ledger({ m, d }) {
  const [rows, setRows] = useState(null)
  const [form, setForm] = useState(false)
  const [e, setE] = useState('')
  const load = () => api('/fin/ledger?ym=' + m).then(setRows, err(setE))
  useEffect(() => { setRows(null); load() }, [m])
  const cancel = id => confirm('Отменить операцию? Она останется в журнале зачёркнутой.') && api(`/fin/ledger/${id}/cancel`, { method: 'POST' }).then(() => { load(); setBk(k => k + 1) }, err(setE))
  const [bk, setBk] = useState(0)   // «Постоянные оплаты» — заново после отмены строки
  return <><Bills key={bk} d={d} onPaid={load} /><div className="card">
    <div className="head"><h3>Движение денег</h3>{!form && <button className="mini" onClick={() => setForm(true)}>+ Операция</button>}</div>
    {form && <LedgerForm d={d} cancel={() => setForm(false)} done={() => { setForm(false); load() }} />}
    {e && <p className="small why">{e}</p>}
    {rows?.map(x => <div key={x.id} className="row" style={x.status === 'cancelled' ? { opacity: .45, textDecoration: 'line-through' } : null}>
      <div><b>{x.direction === 'in' ? '+' : '−'}{money(+x.amount)}</b> {x.article_title}
        <div className="small muted">{[new Date(x.op_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }), x.account_title, x.payee_name,
          x.deal_id && `сделка № ${x.deal_id}`, x.period !== m && `за ${x.period}`, x.note].filter(Boolean).join(' · ')}
          {x.receipt_url && <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></>}</div>
        {x.source === 'bitrix' && x.status === 'active' && <div className="small muted">из Битрикса · счёт:{' '}
          <select className="inline" value={x.account_code} onChange={e => api(`/fin/ledger/${x.id}/account`, { method: 'POST', body: { account: e.target.value } }).then(load, err(setE))}>
            {d.accounts.map(a => <option key={a.code} value={a.code}>{a.title}</option>)}</select></div>}
        {unchecked(x) && <div className="small why">внёс МОП · на сверке: проверьте чек и выписку</div>}</div>
      {unchecked(x) && <button className="mini" onClick={() => api(`/fin/ledger/${x.id}/check`, { method: 'POST' }).then(load, err(setE))}>✓</button>}
      {x.status === 'active' && <button className="ghost mini" onClick={() => cancel(x.id)}>✕</button>}
    </div>)}
    {rows && !rows.length && !form && <p className="small muted">Операций за месяц нет. Начните с «Остаток на начало» по каждому счёту.</p>}
  </div></>
}

function PayRow({ r, m, d, reload }) {
  const [open, setOpen] = useState(false)
  const [v, set] = useState({ amount: '', account: d.accounts[0]?.code, op_date: today(), adj: '', detail: '' })
  const [e, setE] = useState('')
  const pay = () => api(`/fin/payroll/${m}/pay`, { method: 'POST', body: { client_uid: uuid(), payee_id: r.id, amount: +v.amount, account: v.account, op_date: v.op_date } })
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
  return <><Monday d={d} onPaid={load} /><div className="card">
    <div className="head"><h3>ФОТ</h3><button className="mini" disabled={busy} onClick={compute}>{busy ? 'Считаю…' : 'Пересчитать'}</button></div>
    {p && <div className="kv"><div><span className="muted small">Начислено</span><b>{money(p.accrued)}</b></div>
      <div><span className="muted small">Выплачено</span><b>{money(p.paid)}</b></div><div><span className="muted small">Осталось</span><b>{money(p.left)}</b></div></div>}
    <p className="small muted">Пересчёт берёт смены, бонусы печати, оклады, % МОП и возмещение чеков «свои деньги». Ручные начисления не трогает.</p>
    {e && <p className="small why">{e}</p>}
    {p?.rows.map(r => <PayRow key={r.id} r={r} m={m} d={d} reload={load} />)}
  </div></>
}

// Выплаты по понедельникам (HEAD 10.11): саппортам — смены, всем — чеки «свои деньги». «Выплачено» пишет строку в журнал денег.
function Monday({ d, onPaid }) {
  const [w, setW] = useState(null)
  const [e, setE] = useState('')
  const bank = d.accounts.filter(a => a.code !== 'cash')
  const hasCash = d.accounts.some(a => a.code === 'cash')
  const [acc, setAcc] = useState((bank[0] || d.accounts[0])?.code)
  const [busy, setBusy] = useState(0)
  const load = () => api('/fin/weekly').then(setW, err(setE))
  useEffect(() => { load() }, [])
  const [rc, setRc] = useState(null)   // {payee_id, receipt} — чек перевода перед «Выплачено» (HEAD 10.11)
  const pay = r => {
    setBusy(r.payee_id); setE('')
    api('/fin/weekly/pay', { method: 'POST', body: { client_uid: uuid(), payee_id: r.payee_id, account: rc?.cash ? 'cash' : acc, op_date: today(), amount: r.total,
      receipt: rc?.payee_id === r.payee_id ? rc.receipt || null : null } })
      .then(() => { setRc(null); load(); onPaid && onPaid() }, err(setE)).finally(() => setBusy(0))
  }
  const day = w && new Date(w.monday + 'T12:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
  return <div className="card">
    <div className="head"><h3>К выплате в понедельник</h3>{w && <b className="nowrap">{money(w.total)}</b>}</div>
    <p className="small muted">{day ? `Понедельник, ${day}. ` : ''}Саппортам — принятые смены, всем — одобренные чеки «свои деньги». Нажми «Выплачено», когда перевёл: сотрудник увидит «выплачено».</p>
    {e && <p className="small why">{e}</p>}
    {w && w.rows.length > 0 && bank.length > 1 && <select value={acc} onChange={x => setAcc(x.target.value)}>{bank.map(a => <option key={a.code} value={a.code}>Со счёта: {a.title}</option>)}</select>}
    {!w ? <p className="muted small">Загрузка…</p> : !w.rows.length ? <p className="small muted">Всё выплачено.</p> :
      w.rows.map(r => <div key={r.payee_id} className="row">
        <div><b>{r.name}</b> · {money(r.total)}
          <div className="small muted">{r.lines.map(x => `${x.what} за ${x.ym.slice(5)}.${x.ym.slice(0, 4)}: ${money(x.amount)}`).join(' · ')}{r.checks ? ` · чеков ${r.checks}` : ''}</div></div>
        {rc?.payee_id === r.payee_id ? null : <button className="mini" onClick={() => setRc({ payee_id: r.payee_id, receipt: '', cash: false })}>Выплачено</button>}
        {rc?.payee_id === r.payee_id && <div className="dealedit" style={{ flexBasis: '100%' }}>
          <div className="seg"><button className={rc.cash ? 'ghost' : ''} onClick={() => setRc({ ...rc, cash: false })}>Переводом</button>
            {hasCash && <button className={rc.cash ? '' : 'ghost'} onClick={() => setRc({ ...rc, cash: true, receipt: '' })}>Наличными</button>}</div>
          {rc.cash ? <p className="small muted">Наличные — без чека. Сотрудник нажмёт «Получил» в «Мои выплаты», здесь появится дата.</p>
            : <Receipt value={rc.receipt} pick={async f => setRc({ ...rc, receipt: await shrink(f) })} />}
          <div className="seg"><button disabled={busy === r.payee_id} onClick={() => pay(r)}>Выплачено {money(r.total)}</button><button className="ghost" onClick={() => setRc(null)}>Отмена</button></div></div>}
      </div>)}
    {w && w.paid?.length > 0 && <details className="paidlog"><summary className="small">Уже выплачено (45 дней): {w.paid.length}</summary>
      {w.paid.map(x => <div key={x.id} className="row"><div><b>{x.name}</b> · {money(+x.amount)}
        <div className="small muted">{new Date(x.op_date + 'T12:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })} · {x.account} · за {x.period}{x.account_code === 'cash' ? (x.ack_at ? ' · получил ' + new Date(x.ack_at).toLocaleDateString('ru-RU') : ' · ждёт «Получил»')
          : x.receipt_url ? <> · <a href={x.receipt_url}>чек</a></> : ' · без чека'}</div></div></div>)}</details>}
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
      {['salary', 'shifts'].includes(v.scheme) && <><input inputMode="numeric" value={v.amount ?? ''} onChange={e => set({ ...v, amount: e.target.value.replace(/\D/g, '') })} placeholder={v.scheme === 'shifts' ? 'Оклад сверх смен, ₸ (если есть)' : 'Оклад в месяц, ₸'} />
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

// «Обзор» (HEAD 09.11: «с диаграммами, графиками — как в артефакте финансов»): год графиками, тап по месяцу — его цифры
const COSTS = [['payroll', 'ФОТ', '#E60041'], ['project', 'На объекты', '#3DDC97'], ['materials', 'Материалы', '#5CD3E6'], ['stock', 'Склад', '#F3C38A'],
  ['canvas', 'Мастерская', '#C58CFF'], ['sales', 'Отдел продаж', '#7FA8FF'], ['fixed', 'Постоянные', '#9C97A0'], ['variable', 'Переменные', '#FF8A5C']]
export function Overview({ openMonth }) {
  const [y, setY] = useState(new Date().getFullYear())
  const [d, setD] = useState(null)
  const [e, setE] = useState('')
  const [pick, setPick] = useState(null)
  useEffect(() => { setD(null); setE(''); api('/fin/year?y=' + y).then(setD, err(setE)) }, [y])
  if (e) return <div className="card"><p className="small muted">{e}</p></div>
  if (!d) return <div className="card muted">Считаю год…</div>
  const ms = d.months.map(m => ({ ...m, spent: Object.values(m.costs).reduce((a, x) => a + (x || 0), 0) }))
  const sum = k => ms.reduce((a, m) => a + (m[k] || 0), 0)
  const net = sum('net'), gross = sum('gross'), spent = sum('spent'), profit = sum('profit'), deals = sum('deals')
  const pm = ms.find(m => m.month === pick) || ms[ms.length - 1]
  const costs = COSTS.map(([k, t, c]) => ({ t, c, v: ms.reduce((a, m) => a + (m.costs[k] || 0), 0) })).sort((a, b) => b.v - a.v)
  const best = [...ms].sort((a, b) => (b.net || 0) - (a.net || 0))[0]
  const MN = m => new Date(m + '-01').toLocaleDateString('ru-RU', { month: 'long' })
  return <>
    <div className="card dark fin-hero">
      <div className="head"><button className="ghost mini" onClick={() => setY(y - 1)}>‹</button><b>{y} год</b>
        <button className="ghost mini" disabled={y >= new Date().getFullYear()} onClick={() => setY(y + 1)}>›</button></div>
      <div className="kpis">
        <div><span>Выручка с НДС</span><b>{mln(gross)}</b></div>
        <div><span>Без НДС</span><b>{mln(net)}</b></div>
        <div><span>Прибыль до ИПН</span><b className={profit < 0 ? 'neg' : 'pos'}>{mln(profit)}</b></div>
        <div><span>Маржа</span><b>{net ? Math.round(profit / net * 100) + '%' : '—'}</b></div>
        <div><span>Сделок сдано</span><b>{deals || '—'}</b></div>
        <div><span>Средний чек</span><b>{deals ? mln(gross / deals) : '—'}</b></div>
      </div></div>
    <div className="card"><h3>Выручка и прибыль по месяцам</h3>
      <MonthBars months={ms} picked={pm?.month} onPick={setPick} />
      <div className="legend"><span><i style={{ background: 'var(--text)' }} />Выручка без НДС</span><span><i style={{ background: '#4A4652' }} />Расходы</span>
        <span><i style={{ background: 'var(--accent)' }} />Прибыль</span>{ms.some(m => m.estimate) && <span><i style={{ background: 'var(--muted)' }} />до ноября — история</span>}</div>
      {pm && <div className="fin-month">
        <div className="head"><b>{MN(pm.month)}</b>{openMonth && <button className="ghost mini" onClick={() => openMonth(pm.month)}>Сводка месяца ›</button>}</div>
        <div className="kpis">
          <div><span>Выручка без НДС</span><b>{mln(pm.net)}</b></div><div><span>Расходы</span><b>{mln(pm.spent)}</b></div>
          <div><span>Прибыль</span><b className={pm.profit < 0 ? 'neg' : 'pos'}>{mln(pm.profit)}</b></div><div><span>Сделок</span><b>{pm.deals}</b></div>
        </div></div>}
      <p className="small muted">Тапните месяц на графике — ниже его цифры. {best?.net ? `Лучший месяц — ${MN(best.month)}, ${mln(best.net)}.` : ''}</p></div>
    <div className="card"><h3>Куда уходят деньги · {y}</h3><Donut parts={costs} label="расходы" /></div>
    {d.cities.length > 0 && <div className="card"><h3>Выручка по городам</h3><HBars rows={d.cities.slice(0, 8).map(c => ({ t: c.city, v: c.sum }))} /></div>}
    <div className="card"><h3>Деньги: пришло и ушло</h3>
      <HBars rows={[{ t: 'Пришло', v: sum('cash_in'), c: '#3DDC97' }, { t: 'Ушло', v: sum('cash_out'), c: '#E60041' }]} />
      <p className="small muted">По журналу денег с ноября: оплаты Битрикса подтягиваются сами, остальное — «Деньги».</p></div>
  </>
}

export function Finance({ initial }) {
  const [m, setM] = useState(ym())
  const [t, setT] = useState(initial || 'over')
  const [d, setD] = useState(null)
  const [e, setE] = useState('')
  useEffect(() => { api('/fin/dict').then(setD, err(setE)) }, [])
  if (e) return <div className="card"><p className="muted">{e}</p></div>
  if (!d) return <div className="card muted">Загрузка…</div>
  return <>
    <div className="card">{t !== 'over' && <MonthBar m={m} setM={setM} />}
      <div className="segf">{[['over', 'Обзор'], ['sum', 'Месяц'], ['cash', 'Деньги'], ['pay', 'ФОТ'], ['buy', 'Закупки'], ['who', 'Люди']].map(([k, n]) =>
        <button key={k} className={t === k ? 'on' : ''} onClick={() => setT(k)}>{n}</button>)}</div></div>
    {t === 'over' ? <Overview openMonth={x => { setM(x); setT('sum') }} /> : t === 'sum' ? <Summary m={m} /> : t === 'cash' ? <Ledger m={m} d={d} /> : t === 'pay' ? <Payroll m={m} d={d} /> : t === 'buy' ? <StockSpend /> : <Payees d={d} />}
  </>
}

// ---------- закупки на склад: все роли, по каталогу журнала закупок (HEAD 06.11) ----------
// Ориентир цены задаёт HEAD, потолок = ориентир + допуск из «Значений». В пределах потолка — принято само,
// выше потолка или без ориентира — ждёт HEAD. Лимитов нет. Деньги — в финансы, статья «Склад» / «Мастерская холстов».

const FL = { ok: ['🟢', 'в норме'], above_ref: ['🟡', 'выше ориентира'], over_cap: ['🔴', 'выше потолка — к HEAD'], no_ref: ['⚪', 'нет ориентира — к HEAD'] }
const flagOf = (unit, it) => it?.ref_price == null ? 'no_ref' : unit > it.cap_price + .005 ? 'over_cap' : unit > it.ref_price + .005 ? 'above_ref' : 'ok'
const num = s => s.replace(',', '.').replace(/[^\d.]/g, '')

function PurchaseForm({ cat, done, cancel }) {
  const [dept, setDept] = useState(cat.home)
  const [q, setQ] = useState('')
  const [lines, setLines] = useState([])          // { key, item_code?, name, qty, amount }
  const [v, set] = useState({ paid_by: 'own', note: '', deal_id: '', receipt: '' })
  const [busy, setBusy] = useState(false)
  const items = cat.items.filter(i => i.active && i.dept === dept && (!q || i.name.toLowerCase().includes(q.toLowerCase())))
  const byCode = Object.fromEntries(cat.items.map(i => [i.code, i]))
  const add = it => setLines(l => l.some(x => x.item_code === it.code) ? l : [...l, { key: it.code, item_code: it.code, name: it.name, qty: '1', amount: it.ref_price ? String(it.ref_price) : '' }])
  const own = () => setLines(l => [...l, { key: 'own' + Date.now(), name: q, qty: '1', amount: '' }])
  const upd = (k, f) => setLines(l => l.map(x => x.key === k ? { ...x, ...f } : x))
  const flags = lines.map(x => +x.qty > 0 && +x.amount > 0 ? flagOf(+x.amount / +x.qty, x.item_code && byCode[x.item_code]) : null)
  const total = lines.reduce((s, x) => s + (+x.amount || 0), 0)
  const ready = lines.length && lines.every(x => +x.qty > 0 && +x.amount > 0 && (x.item_code || x.name.trim())) && v.receipt
  const toHead = flags.some(f => f === 'over_cap' || f === 'no_ref')
  const send = async () => {
    setBusy(true)
    const n = await enqueue('/stock/purchase', { dept, paid_by: v.paid_by, receipt: v.receipt, note: v.note || null, deal_id: +v.deal_id || null,
      lines: lines.map(x => ({ item_code: x.item_code || null, name: x.item_code ? null : x.name.trim(), qty: +x.qty, amount: +x.amount })) })
    setBusy(false)
    done(n ? 'Сохранено на телефоне, отправится, когда будет сеть.' : toHead ? 'Покупка ушла на одобрение HEAD.' : 'Покупка записана.')
  }
  let sec = null
  return <div className="dealedit">
    <div className="chips scroll">{cat.depts.map(d => <button key={d.code} className={dept === d.code ? 'on' : ''} onClick={() => { setDept(d.code); setLines([]) }}>{d.title}</button>)}</div>
    <input value={q} onChange={e => setQ(e.target.value)} placeholder="Найти позицию" />
    <div className="catlist">{items.map(it => {
      const head = it.section !== sec ? (sec = it.section) : null
      const inCart = lines.some(x => x.item_code === it.code)
      return <React.Fragment key={it.code}>{head && <div className="catsec">{head}</div>}
        <button className={'catitem' + (inCart ? ' on' : '')} onClick={() => add(it)}>
          <span>{it.name}<small>{[it.unit, it.where_buy].filter(Boolean).join(' · ')}</small></span>
          <b>{it.ref_price != null ? money(it.ref_price) : '—'}{it.cap_price != null && <small>до {money(it.cap_price)}</small>}</b></button></React.Fragment>
    })}
      {!items.length && <p className="small muted">Ничего не нашлось.</p>}
      <button className="ghost mini" onClick={own}>+ Нет в списке{q ? `: «${q}»` : ''}</button></div>
    {lines.length > 0 && <div className="cart"><b>Купил</b>
      {lines.map((x, i) => { const it = x.item_code && byCode[x.item_code]; const f = flags[i]
        return <div key={x.key} className="cartline">
          {x.item_code ? <div>{x.name}<span className="small muted"> · {it?.unit || 'ед.'}{it?.ref_price != null ? ` · ориентир ${money(it.ref_price)}, потолок ${money(it.cap_price)}` : ' · ориентира нет'}</span></div>
            : <input value={x.name} onChange={e => upd(x.key, { name: e.target.value })} placeholder="Что купил" />}
          <div className="cartnums small muted"><span>Сколько, {it?.unit || 'ед.'}</span><span>Сумма по чеку, ₸</span><i style={{ width: 40 }} /></div>
          <div className="cartnums">
            <input inputMode="decimal" value={x.qty} onChange={e => upd(x.key, { qty: num(e.target.value) })} placeholder="Кол-во" aria-label="Количество" />
            <input inputMode="numeric" value={x.amount} onChange={e => upd(x.key, { amount: e.target.value.replace(/\D/g, '') })} placeholder="Сумма, ₸" aria-label="Сумма" />
            <button className="ghost mini" onClick={() => setLines(l => l.filter(y => y.key !== x.key))} aria-label="Убрать">✕</button></div>
          {f && <div className="small">{FL[f][0]} {money(Math.round(+x.amount / +x.qty))} за ед. — {FL[f][1]}</div>}</div> })}
      <div className="row"><span>Итого по чеку</span><b>{money(total)}</b></div></div>}
    <div className="segf"><button className={v.paid_by === 'own' ? 'on' : ''} onClick={() => set({ ...v, paid_by: 'own' })}>Свои деньги</button>
      <button className={v.paid_by === 'company' ? 'on' : ''} onClick={() => set({ ...v, paid_by: 'company' })}>Деньги компании</button></div>
    <input value={v.note} onChange={e => set({ ...v, note: e.target.value })} placeholder="Комментарий (магазин, зачем срочно)" />
    <input inputMode="numeric" value={v.deal_id} onChange={e => set({ ...v, deal_id: e.target.value.replace(/\D/g, '') })} placeholder="№ сделки, если под проект (не обязательно)" />
    <Receipt value={v.receipt} need pick={async f => set({ ...v, receipt: await shrink(f) })} />
    {lines.length > 0 && <p className={'small ' + (toHead ? 'why' : 'muted')}>{toHead ? 'Есть цена выше потолка или позиция без ориентира — покупка уйдёт на одобрение HEAD.' : 'Все цены в пределах потолка — покупка примется сразу.'}</p>}
    <div className="dealbtns"><button disabled={busy || !ready} onClick={send}>Записать покупку</button>
      <button className="ghost" onClick={cancel}>Отмена</button></div>
  </div>
}

// HEAD: ориентиры цен и позиции каталога. Потолок считается сам из допуска в «Значениях».
function Catalog({ cat, reload }) {
  const [dept, setDept] = useState(cat.home === 'household' ? cat.depts[0]?.code : cat.home)
  const [ed, setEd] = useState(null)
  const [e, setE] = useState('')
  const save = () => api(ed.code ? '/stock/items/' + encodeURIComponent(ed.code) : '/stock/items', { method: 'POST',
    body: { dept: ed.dept, name: ed.name, section: ed.section || null, unit: ed.unit || null, ref_price: ed.ref_price === '' || ed.ref_price == null ? null : +ed.ref_price,
      where_buy: ed.where_buy || null, norm: ed.norm || null, active: ed.active } }).then(() => { setEd(null); setE(''); reload() }, err(setE))
  return <>
    <p className="small muted">Допуск над ориентиром: {cat.tolerance != null ? cat.tolerance + ' %' : 'не задан в «Значениях» (stock.price_tolerance_pct) — потолок = ориентир'}.</p>
    <div className="chips scroll">{cat.depts.map(d => <button key={d.code} className={dept === d.code ? 'on' : ''} onClick={() => setDept(d.code)}>{d.title}</button>)}</div>
    {ed ? <div className="dealedit">
      <input value={ed.name} onChange={x => setEd({ ...ed, name: x.target.value })} placeholder="Позиция" />
      <input value={ed.section || ''} onChange={x => setEd({ ...ed, section: x.target.value })} placeholder="Раздел" />
      <input value={ed.unit || ''} onChange={x => setEd({ ...ed, unit: x.target.value })} placeholder="Единица (шт, уп. 10 шт)" />
      <input inputMode="numeric" value={ed.ref_price ?? ''} onChange={x => setEd({ ...ed, ref_price: x.target.value.replace(/\D/g, '') })} placeholder="Ориентир за единицу, ₸" />
      <input value={ed.where_buy || ''} onChange={x => setEd({ ...ed, where_buy: x.target.value })} placeholder="Где брать" />
      <input value={ed.norm || ''} onChange={x => setEd({ ...ed, norm: x.target.value })} placeholder="Норма склада" />
      {e && <p className="small why">{e}</p>}
      <div className="dealbtns"><button disabled={!ed.name.trim()} onClick={save}>Сохранить</button>
        {ed.code && <button className="ghost" onClick={() => setEd({ ...ed, active: !ed.active })}>{ed.active ? 'Выключить' : 'Включить'}</button>}
        <button className="ghost" onClick={() => setEd(null)}>Отмена</button></div></div>
      : <button className="ghost mini" onClick={() => setEd({ dept, name: '', active: true })}>+ Позиция</button>}
    {cat.items.filter(i => i.dept === dept).map(i => <div key={i.code} className="row" style={{ cursor: 'pointer', opacity: i.active ? 1 : .45 }}
      onClick={() => setEd({ ...i, ref_price: i.ref_price ?? '' })}>
      <span>{i.name}<div className="small muted">{[i.code, i.unit, i.where_buy, i.fact_price != null && 'факт ' + money(i.fact_price)].filter(Boolean).join(' · ')}</div></span>
      <b className={i.ref_price == null ? 'muted' : ''}>{i.ref_price != null ? money(i.ref_price) : 'нет'}</b></div>)}
  </>
}

export function StockSpend() {
  const [m, setM] = useState(null)
  const [cat, setCat] = useState(null)
  const [e, setE] = useState('')
  const [form, setForm] = useState(false)
  const [view, setView] = useState('buy')
  const [msg, setMsg] = useState('')
  const load = () => api('/stock/expenses').then(setM, err(setE))
  const loadCat = () => api('/stock/catalog').then(setCat, err(setE))
  // ошиблись разделом (такси — это «Траты», не «Склад») — отменить свою покупку, пока не выплачено
  const drop = x => confirm(`Отменить покупку на ${money(+x.amount)}? Она уйдёт из лимита и возмещения.`) &&
    api(`/stock/expenses/${x.id}/cancel`, { method: 'POST' }).then(() => { setMsg('Покупка отменена.'); load(); loadCat() }, ex => setMsg('Не отменилось: ' + ex.message))
  useEffect(() => { load(); loadCat(); const f = () => load(); window.addEventListener('artgame:queue', f); return () => window.removeEventListener('artgame:queue', f) }, [])
  if (e) return <div className="card"><h3>Склад</h3><p className="small muted">{e}</p></div>
  if (!m || !cat) return <div className="card muted">Загрузка…</div>
  return <div className="card">
    <div className="head"><h3>{m.all ? 'Закупки на склад' : 'Склад'} {m.total > 0 && <span className="muted small">{money(m.total)} за месяц</span>}</h3>
      {!form && view === 'buy' && <button className="mini" onClick={() => { setForm(true); setMsg('') }}>+ Покупка</button>}</div>
    {cat.head && <div className="segf"><button className={view === 'buy' ? 'on' : ''} onClick={() => setView('buy')}>Покупки</button>
      <button className={view === 'cat' ? 'on' : ''} onClick={() => { setView('cat'); setForm(false) }}>Каталог и цены</button></div>}
    {view === 'cat' ? <Catalog cat={cat} reload={loadCat} /> : <>
    {!form && <p className="small muted">Купил что-то на склад — отметь здесь: что, сколько, за сколько, и фото чека. Цена в пределах потолка — принято сразу, выше — решает HEAD.</p>}
    {m.waiting > 0 && m.all && <p className="small why">Ждут одобрения: {m.waiting} — во вкладке «Проверка».</p>}
    {form && <PurchaseForm cat={cat} cancel={() => setForm(false)} done={t => { setForm(false); setMsg(t); load(); loadCat() }} />}
    {msg && <p className="small muted">{msg}</p>}
    {pending() > 0 && <p className="small muted">Ждут сети: {pending()}</p>}
    {m.items.map(x => <div key={x.id} className="row">
      <div><b>{money(+x.amount)}</b> {x.category_title}{m.all ? ' · ' + x.person : ''}
        <div className="small muted">{[new Date(x.created_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }), x.note, x.deal_id && `сделка № ${x.deal_id}`,
          x.paid_by === 'company' ? 'деньги компании' : x.payout_status === 'to_pay' ? 'к выплате' : x.payout_status === 'paid' ? 'выплачено' : ''].filter(Boolean).join(' · ')}
          {x.receipt_url && <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></>}</div>
        {x.reason && x.status === 'rejected' && <div className="small">Причина: {x.reason}</div>}</div>
      <div className="qbtns"><span className={'tag st-' + x.status}>{ST[x.status] || x.status}</span>
        {(x.person_id === m.me || m.all) && ['submitted', 'approved'].includes(x.status) && x.payout_status !== 'paid' &&
          <button className="ghost mini" onClick={() => drop(x)}>Отменить</button>}</div>
    </div>)}
    {!m.items.length && !form && <p className="small muted">В этом месяце покупок нет.</p>}</>}
  </div>
}

// ---------- мои выплаты: каждый видит только своё ----------

const LINE = { piece: 'Смены', bonus: 'Бонус', topup: 'Доплата до минимума', salary: 'Оклад', mop_pct: '% от выручки', mop_bonus: 'Бонус за план',
  reimburse: 'Возмещение чеков', manual: 'Начисление HEAD', design_units: 'Единицы дизайна сверх нормы', catalog: 'Каталог референсов', reels: 'Рилс (утверждены HEAD)', trip_food: 'Суточные в командировке' }
export function MyPay() {
  const [m, setM] = useState(ym())
  const [p, setP] = useState(null)
  useEffect(() => { setP(null); api('/fin/my?ym=' + m).then(setP, () => setP({ lines: [], accrued: 0, paid: 0, left: 0 })) }, [m])
  return <div className="card"><h3>Мои выплаты</h3><MonthBar m={m} setM={setM} />
    {p && <><div className="kv"><div><span className="muted small">Начислено</span><b>{money(p.accrued)}</b></div>
      <div><span className="muted small">Выплачено</span><b>{money(p.paid)}</b></div><div><span className="muted small">Осталось</span><b>{money(p.left)}</b></div></div>
      {p.lines.map((a, i) => <div key={i} className="row small"><span>{a.detail || LINE[a.kind]}</span><b>{money(+a.amount)}</b></div>)}
      {!p.lines.length && <p className="small muted">{p.live ? 'Принятых смен за этот месяц пока нет. Как только смену примут — сумма появится здесь сразу.' : 'За этот месяц начислений пока нет.'}</p>}
      {p.live && p.lines.length > 0 && <p className="small muted">Считается сразу по принятым сменам. Окончательно — когда HEAD закроет месяц.</p>}
      {p.payments?.length > 0 && <><h3 style={{ marginTop: 14 }}>Выплаты</h3>
        {p.payments.map(x => <div key={x.id} className="row small"><div><b>{money(+x.amount)}</b>
          <div className="muted">{new Date(x.op_date + 'T12:00').toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })} · {x.account}
            {x.receipt_url && <> · <a href={x.receipt_url}>чек</a></>}{x.ack_at && ' · получил ' + new Date(x.ack_at).toLocaleDateString('ru-RU')}</div></div>
          {!x.ack_at && <button className="mini" onClick={() => api('/fin/my/ack/' + x.id, { method: 'POST' }).then(() => setP({ ...p,
            payments: p.payments.map(y => y.id === x.id ? { ...y, ack_at: new Date().toISOString() } : y) }))}>Получил</button>}</div>)}
        <p className="small muted">Нажми «Получил», когда деньги пришли (особенно наличные).</p></>}
      {p.rate?.length > 0 && <><h3 style={{ marginTop: 14 }}>Моя ставка</h3>
        {p.rate.map((r, i) => <div key={i} className="row small"><span>{r.label}</span><b>{money(r.amount)}</b></div>)}
        <p className="small muted">По листу «Значения». Изменения ставок утверждает HEAD.</p></>}</>}
  </div>
}

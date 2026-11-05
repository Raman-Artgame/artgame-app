import React, { useEffect, useState } from 'react'
import { api } from './api.js'

const money = n => n ? Math.round(n).toLocaleString('ru-RU') + ' ₸' : '—'
const dt = s => s ? new Date(s).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''
const strip = s => (s || '').replace(/<[^>]+>/g, '').replace(/\[\/?[A-Za-z]+\]/g, '')

// Карточка сделки в приложении: всё из Битрикса на одном экране. Битрикс — источник правды, здесь только показ и действия.
const LEVELS = { easy: 'Лёгкий', medium: 'Средний', hard: 'Сложный', author: 'Авторский' }
export function DealCard({ id, back, open }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [calc, setCalc] = useState(null)   // форма расчёта: {area, level, service, height, outdoor}
  const [msg, setMsg] = useState('')
  const load = fresh => api(`/bx/deals/${id}/full${fresh ? '?fresh=1' : ''}`).then(setD, e => setErr(e.message))
  useEffect(() => { load(false) }, [id])
  const runCalc = () => api(`/bx/deals/${id}/calc`, { method: 'POST', body: { ...calc, area: +calc.area } }).then(r => {
    setCalc(null); const c = r.calc
    setMsg(`По норме: ${c.shifts} смен, ${c.crew} чел., ${c.client} раб. дн. клиенту. ` + (r.bx === 'off' ? 'В Битрикс не записано: ключ записи ещё не задан.' : !r.norm_fields ? 'В Битриксе ещё нет полей для смен и срока (задание Кодексу), записаны площадь и комментарий.' : 'Записано в сделку.'))
    load(true)
  }, e => setMsg('Не записалось: ' + e.message))
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
    <div className="card"><h3>Срок и ресурсы <span className="muted small">считает приложение</span></h3>
      {d.norm.shifts ? <div className="kv">
        <div><span className="muted small">Смен по норме</span><b>{d.norm.shifts}</b></div>
        <div><span className="muted small">Художников</span><b>{d.norm.crew}</b></div>
        <div><span className="muted small">Срок клиенту</span><b>{d.norm.term} раб. дн.</b></div>
        <div><span className="muted small">Сложность</span><b>{LEVELS[d.level] || '—'}</b></div>
      </div> : <p className="small muted">Расчёта ещё не было: смены, люди и срок появятся после расчёта, руками не вводятся.</p>}
      {msg && <p className="small muted">{msg}</p>}
      {!calc ? <div className="dealbtns"><button className="ghost" onClick={() => setCalc({ area: d.area || '', level: d.level || 'medium', service: 'mural', height: false, outdoor: false })}>{d.norm.shifts ? 'Пересчитать' : 'Сделать расчёт'}</button></div>
      : <div className="dealedit">
        <div className="seg"><button className={calc.service === 'mural' ? '' : 'ghost'} onClick={() => setCalc({ ...calc, service: 'mural' })}>Роспись</button><button className={calc.service === 'print' ? '' : 'ghost'} onClick={() => setCalc({ ...calc, service: 'print' })}>Печать</button></div>
        <input type="number" min="1" value={calc.area} onChange={e => setCalc({ ...calc, area: e.target.value })} placeholder="Площадь, м²" />
        {calc.service === 'mural' && <select value={calc.level} onChange={e => setCalc({ ...calc, level: e.target.value })}>{Object.entries(LEVELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}
        {calc.service === 'mural' && <div className="dealbtns"><button className={calc.height ? '' : 'ghost'} onClick={() => setCalc({ ...calc, height: !calc.height })}>Высота</button><button className={calc.outdoor ? '' : 'ghost'} onClick={() => setCalc({ ...calc, outdoor: !calc.outdoor })}>Улица</button></div>}
        <button disabled={!(+calc.area > 0)} onClick={runCalc}>Посчитать и записать в сделку</button>
        <p className="small muted">Нормы из «Значений»: м² за смену по сложности, 1 человек на 20 м², подготовка, запас 20% клиенту.</p>
      </div>}
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
  const total = t.back.length + t.new.length + t.kp.length + t.idle.length + t.tasks.length
  return <>
    <div className="card"><h2>Сегодня</h2><p className="muted">{total ? `Требуют действия: ${total}` : 'Всё в порядке, срочного нет.'}</p></div>
    {!!t.back.length && <div className="card"><h3>Пора вернуться <span className="muted small">{t.back.length}</span></h3>
      <p className="small muted">Отложенные сделки, у которых подошла дата возврата.</p>
      {t.back.map(d => <div key={d.id} className="row" onClick={() => openDeal(d.id)}><div><b>№ {d.id}</b> {d.title.replace(new RegExp(`^№?\\s*${d.id}\\s*·?\\s*`), '')}<div className="muted small">до {d.due.split('-').reverse().join('.')}{d.note ? ' · ' + d.note : ''}</div></div><a>открыть</a></div>)}
    </div>}
    {block('Новые заявки без ответа', t.new, `В «Взаимном информировании» дольше ${L.new_hours} ч.`)}
    {block('КП без ответа', t.kp, `После отправки КП прошло ${L.kp_days}+ дня.`)}
    {block('Сделки без движения', t.idle, `Нет изменений ${L.idle_days}+ дня (кроме «Отложено»).`)}
    <div className="card"><h3>Задачи в Битриксе <span className="muted small">{t.tasks.length}</span></h3>
      {!t.tasks.length && <p className="muted small">Открытых задач нет.</p>}
      {t.tasks.map(x => <div key={x.id} className="row" onClick={() => x.deal && openDeal(x.deal)}><div>{x.title}{x.deal && <div className="muted small">сделка № {x.deal}</div>}</div><span className="muted small">{x.deadline ? x.deadline.slice(0, 10) : ''}</span></div>)}
    </div>
  </>
}

// «Мой месяц»: выигранные сделки месяца из Битрикса, выручка без НДС, ступень и % по «Значениям» (pay.mop.*). HEAD видит всех.
const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const ymName = ym => { const [y, m] = ym.split('-'); return `${MONTHS[+m - 1]} ${y}` }
const ymShift = (ym, k) => { const [y, m] = ym.split('-').map(Number); const d = new Date(y, m - 1 + k, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }
export function Month({ openDeal }) {
  const now = new Date()
  const [ym, setYm] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const [m, setM] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { setM(null); api(`/bx/month?ym=${ym}`).then(setM, e => setErr(e.message)) }, [ym])
  const cur = ym >= `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const nav = <div className="seg"><button className="ghost" onClick={() => setYm(ymShift(ym, -1))}>←</button><button className="ghost" disabled>{ymName(ym)}</button><button className="ghost" disabled={cur} onClick={() => setYm(ymShift(ym, 1))}>→</button></div>
  if (err) return <div className="card"><h2>Мой месяц</h2>{nav}<p className="muted">{err}</p></div>
  if (!m) return <div className="card"><h2>Мой месяц</h2>{nav}<p className="muted">Считаю по Битриксу…</p></div>
  const steps = m.steps.filter(s => s.from)
  const co = m.company
  const deals = (ds, showMgr) => ds.map(d => <div key={d.id} className="row" onClick={() => openDeal(d.id)}><div><b>№ {d.id}</b> {d.title.replace(new RegExp(`^№?\\s*${d.id}\\s*·?\\s*`), '')}<div className="muted small">{[d.closed.split('-').reverse().join('.'), showMgr && d.manager].filter(Boolean).join(' · ')}</div></div><b>{money(d.sum)}</b></div>)
  return <>
    <div className="card"><h2>{m.all ? 'Месяц команды' : 'Мой месяц'}</h2>{nav}
      <div className="kv">
        <div><span className="muted small">Выручка компании без НДС</span><b>{money(co.net)}</b></div>
        <div><span className="muted small">С НДС{m.vat ? ` ${m.vat}%` : ''}</span><b>{money(co.gross)}</b></div>
        <div><span className="muted small">Ступень</span><b>{co.step ? `${co.step} · ${co.pct}%` : steps.length ? 'пока нет' : '—'}</b></div>
        <div><span className="muted small">Процент МОП</span><b>{money(co.bonus)}{co.plan_bonus ? ` + ${money(co.plan_bonus)}` : ''}</b></div>
      </div>
      {co.next && <p className="small muted">До ступени {co.next.step} ({steps[co.next.step - 1]?.pct}%) не хватает {money(co.next.left)} без НДС.</p>}
      {!!m.salary && <p className="small muted">Оклад {money(m.salary)} + процент от всей выручки компании за месяц без НДС{steps.length ? ': ' + steps.map(s => `${s.pct}% от ${money(s.from)}`).join(', ') : ''}. Считает сервер по закрытым сделкам Битрикса, выплаты отмечает HEAD.</p>}
    </div>
    {m.all && m.managers.map(x => <div key={x.id} className="card"><h3>{x.name} <span className="muted small">{x.count}</span></h3>
      <div className="kv"><div><span className="muted small">Без НДС</span><b>{money(x.net)}</b></div><div><span className="muted small">С НДС</span><b>{money(x.gross)}</b></div></div>
      {deals(x.deals, false)}</div>)}
    {!m.all && <div className="card"><h3>Мои закрытые сделки <span className="muted small">{m.mine.count}</span></h3>
      <div className="kv"><div><span className="muted small">Без НДС</span><b>{money(m.mine.net)}</b></div><div><span className="muted small">С НДС</span><b>{money(m.mine.gross)}</b></div></div>
      {!m.mine.count && <p className="muted small">В этом месяце пока нет.</p>}
      {deals(m.mine.deals, false)}
    </div>}
  </>
}

import React, { useEffect, useState } from 'react'
import { api } from './api.js'

import { CallOutcome, Contact, Feed, cleanTitle, dt, money, strip } from './crm.jsx'

// Карточка сделки: шаги клиент → расчёт → КП → договор → оплата, следующий подсвечен. Битрикс — источник правды.
const LEVELS = { easy: 'Лёгкий', medium: 'Средний', hard: 'Сложный', author: 'Авторский' }
const POSTPONED = 'UC_VCP4VO'   // «Отложено»: только с датой возврата
const KP_ON = new Set(['PREPARATION', 'UC_VZFPUP', 'UC_YV66BV', 'UC_1EXUAC', 'FINAL_INVOICE', 'UC_AV00QK'])
const DOG_ON = new Set(['FINAL_INVOICE', 'UC_AV00QK'])
const tomorrow = () => new Date(Date.now() + 86400000).toISOString().slice(0, 10)
function steps(d) {
  const has = t => d.files.some(f => f.title.startsWith(t))
  return [['Клиент', !!(d.client?.phone || d.client?.name)], ['Расчёт', !!d.norm.shifts || !!d.area], ['КП', KP_ON.has(d.stage) || has('КП')],
    ['Договор', DOG_ON.has(d.stage) || has('Договор')], ['Оплата', d.pay.received > 0]]
}
export function DealCard({ id, back, open }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [calc, setCalc] = useState(null)   // форма расчёта: {area, level, service, height, outdoor}
  const [edit, setEdit] = useState(null)   // {kind: 'stage'|'note', ...}
  const [stages, setStages] = useState([])
  const [msg, setMsg] = useState('')
  const [calcMsg, setCalcMsg] = useState('')
  const load = fresh => api(`/bx/deals/${id}/full${fresh ? '?fresh=1' : ''}`).then(setD, e => setErr(e.message))
  useEffect(() => { load(false); api('/bx/stages').then(setStages, () => {}) }, [id])
  const said = r => r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Записано в Битрикс.'
  const send = (path, body) => api(`/bx/deals/${id}/${path}`, { method: 'POST', body }).then(r => { setEdit(null); setMsg(said(r)); load(true) }, e => setMsg('Не записалось: ' + e.message))
  const runCalc = () => api(`/bx/deals/${id}/calc`, { method: 'POST', body: { ...calc, area: +calc.area } }).then(r => {
    setCalc(null); const c = r.calc
    setCalcMsg(`По норме: ${c.shifts} смен, ${c.crew} чел., ${c.client} раб. дн. клиенту. ` + (r.bx === 'off' ? 'В Битрикс не записано.' : !r.norm_fields ? 'В Битриксе ещё нет полей для смен и срока (задание Кодексу), записаны площадь и комментарий.' : 'Записано в сделку.'))
    load(true)
  }, e => setCalcMsg('Не записалось: ' + e.message))
  if (err) return <div className="card"><a onClick={back}>← назад</a><p className="muted">{err}</p></div>
  if (!d) return <div className="card muted">Загружаю сделку № {id}…</div>
  const c = d.client || {}
  const st = steps(d)
  const next = st.findIndex(x => !x[1])
  const stSel = stages.find(s => s.id === edit?.stage)
  return <>
    <div className="card">
      <a onClick={back}>← к сделкам</a>
      <h2>№ {d.id} · {cleanTitle(d.title, d.id)}</h2>
      <span className="tag">{d.stage_name}</span>{d.manager && <span className="tag">{d.manager}</span>}
      <div className="steps">{st.map(([t, ok], i) => <div key={t} className={ok ? 'done' : i === next ? 'next' : ''}><i />{t}</div>)}</div>
      {next >= 0 && <p className="small">Следующий шаг: <b>{st[next][0]}</b></p>}
      <div className="kv">
        <div><span className="muted small">Сумма</span><b>{money(d.sum)}</b></div>
        <div><span className="muted small">Площадь</span><b>{d.area ? d.area + ' м²' : '—'}</b></div>
        <div><span className="muted small">Услуга</span><b>{d.service || '—'}</b></div>
        <div><span className="muted small">Город</span><b>{d.city || '—'}</b></div>
      </div>
      {d.address && <p className="small">{d.address}</p>}
      <Contact phone={c.phone} name={[c.name, d.contact && d.contact !== c.name ? d.contact : ''].filter(Boolean).join(' · ')} entity="deal" id={d.id} />
      <CallOutcome path={`/bx/deals/${id}`} done={() => load(true)} />
      <div className="dealbtns wrapbtns">
        <button className="ghost" onClick={() => open(d.id, 'kp')}>КП</button>
        <button className="ghost" onClick={() => open(d.id, 'docs')}>Документы</button>
        <button className="ghost" onClick={() => setEdit(edit?.kind === 'stage' ? null : { kind: 'stage', stage: d.stage, reason: '', until: '' })}>Стадия</button>
        <button className="ghost" onClick={() => setEdit(edit?.kind === 'note' ? null : { kind: 'note', text: '' })}>Заметка</button>
      </div>
      {edit?.kind === 'stage' && <div className="dealedit">
        <select value={edit.stage} onChange={e => setEdit({ ...edit, stage: e.target.value })}>{stages.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
        {['failure', 'apology'].includes(stSel?.semantic) && <input value={edit.reason} onChange={e => setEdit({ ...edit, reason: e.target.value })} placeholder="Причина отказа (обязательно)" />}
        {edit.stage === POSTPONED && <>
          <label>Вернуться к сделке<input type="date" value={edit.until} min={tomorrow()} onChange={e => setEdit({ ...edit, until: e.target.value })} /></label>
          <input value={edit.reason} onChange={e => setEdit({ ...edit, reason: e.target.value })} placeholder="Почему отложили" />
          <p className="small muted">В Битриксе появится задача с этой датой, бот напомнит утром.</p></>}
        <button disabled={edit.stage === d.stage || (edit.stage === POSTPONED && !edit.until)} onClick={() => send('stage', { stage: edit.stage, reason: edit.reason || null, until: edit.stage === POSTPONED ? edit.until : null })}>Перевести</button></div>}
      {edit?.kind === 'note' && <div className="dealedit">
        <input value={edit.text} onChange={e => setEdit({ ...edit, text: e.target.value })} placeholder="Заметка в ленту сделки" />
        <button disabled={!edit.text.trim()} onClick={() => send('note', { text: edit.text })}>Записать</button></div>}
      {msg && <p className="small muted">{msg}</p>}
    </div>
    <div className="card"><h3>Срок и ресурсы <span className="muted small">считает приложение</span></h3>
      {d.norm.shifts ? <div className="kv">
        <div><span className="muted small">Смен по норме</span><b>{d.norm.shifts}</b></div>
        <div><span className="muted small">Художников</span><b>{d.norm.crew}</b></div>
        <div><span className="muted small">Срок клиенту</span><b>{d.norm.term} раб. дн.</b></div>
        <div><span className="muted small">Сложность</span><b>{LEVELS[d.level] || '—'}</b></div>
      </div> : <p className="small muted">Расчёта ещё не было: смены, люди и срок появятся после расчёта, руками не вводятся.</p>}
      {calcMsg && <p className="small muted">{calcMsg}</p>}
      {!calc ? <button className="ghost" onClick={() => setCalc({ area: d.area || '', level: d.level || 'medium', service: 'mural', height: false, outdoor: false })}>{d.norm.shifts ? 'Пересчитать' : 'Сделать расчёт'}</button>
      : <div className="dealedit">
        <div className="seg"><button className={calc.service === 'mural' ? '' : 'ghost'} onClick={() => setCalc({ ...calc, service: 'mural' })}>Роспись</button><button className={calc.service === 'print' ? '' : 'ghost'} onClick={() => setCalc({ ...calc, service: 'print' })}>Печать</button></div>
        <input type="number" min="1" value={calc.area} onChange={e => setCalc({ ...calc, area: e.target.value })} placeholder="Площадь, м²" />
        {calc.service === 'mural' && <select value={calc.level} onChange={e => setCalc({ ...calc, level: e.target.value })}>{Object.entries(LEVELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>}
        {calc.service === 'mural' && <div className="dealbtns"><button className={calc.height ? '' : 'ghost'} onClick={() => setCalc({ ...calc, height: !calc.height })}>Высота</button><button className={calc.outdoor ? '' : 'ghost'} onClick={() => setCalc({ ...calc, outdoor: !calc.outdoor })}>Улица</button></div>}
        <button disabled={!(+calc.area > 0)} onClick={runCalc}>Посчитать и записать в сделку</button>
        <p className="small muted">Нормы из «Значений»: м² за смену по сложности, 1 человек на 20 м², подготовка, запас 20% клиенту.</p>
      </div>}
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
    {d.comments && <div className="card"><h3>Комментарий сделки</h3><p className="small">{strip(d.comments)}</p></div>}
    <Feed items={d.feed} />
    {!!d.history.length && <div className="card"><h3>Стадии</h3>
      {d.history.map((h, i) => <div key={i} className="row"><span>{h.stage}</span><span className="muted small">{dt(h.at)}</span></div>)}
    </div>}
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
  if (!m) return <div className="card"><h2>Мой месяц</h2>{nav}<p className="muted">Считаю…</p></div>
  const steps = m.steps.filter(s => s.from)
  const co = m.company
  const deals = (ds, showMgr) => ds.map(d => <div key={d.id} className="row" onClick={() => openDeal(d.id)}><div><b>№ {d.id}</b> {d.title.replace(new RegExp(`^№?\\s*${d.id}\\s*·?\\s*`), '')}<div className="muted small">{[d.closed.split('-').reverse().join('.'), d.city, showMgr && d.manager].filter(Boolean).join(' · ')}</div></div><b>{money(d.sum)}</b></div>)
  return <>
    <div className="card"><h2>{m.all ? 'Месяц команды' : 'Мой месяц'}</h2>{nav}
      <div className="kv">
        <div><span className="muted small">Выручка компании без НДС</span><b>{money(co.net)}</b></div>
        <div><span className="muted small">С НДС{m.vat ? ` ${m.vat}%` : ''}</span><b>{money(co.gross)}</b></div>
        <div><span className="muted small">Ступень</span><b>{co.step ? `${co.step} · ${co.pct}%` : steps.length ? 'пока нет' : '—'}</b></div>
        <div><span className="muted small">Процент МОП</span><b>{money(co.bonus)}{co.plan_bonus ? ` + ${money(co.plan_bonus)}` : ''}</b></div>
      </div>
      {co.next && <p className="small muted">До ступени {co.next.step} ({steps[co.next.step - 1]?.pct}%) не хватает {money(co.next.left)} без НДС.</p>}
      {!!m.salary && <p className="small muted">Оклад {money(m.salary)} + процент от всей выручки компании за месяц без НДС{steps.length ? ': ' + steps.map(s => `${s.pct}% от ${money(s.from)}`).join(', ') : ''}. Выплаты отмечает HEAD.</p>}
      <p className="small muted">{m.source === 'sheet' ? 'Выручка — по листу «Проекты» финансовой таблицы (дата завершения работ, с НДС).' : 'Выручка — по дате закрытия сделок в Битриксе.'}</p>
      {m.warn && <p className="small" style={{ color: 'var(--hot)' }}>{m.warn}</p>}
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

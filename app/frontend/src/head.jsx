import React, { useEffect, useState } from 'react'
import { api, setViewAs, viewAs } from './api.js'
import { flush } from './queue.js'
import { money } from './crm.jsx'
import { LABEL } from './journal.jsx'

// Кабинет HEAD — «Пульт» (HEAD 08.11): сверху то, что ждёт решения, дальше деньги месяца, кто сегодня на объектах,
// команда и последние действия. Отсюда же — «Смотреть как сотрудник».
const tm = s => new Date(s).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
const ago = s => { const m = Math.round((Date.now() - new Date(s)) / 60000); return m < 60 ? `${m} мин` : m < 1440 ? `${Math.round(m / 60)} ч` : `${Math.round(m / 1440)} дн` }
const ym = () => new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Almaty' }).slice(0, 7)
const ZONE = { mural: 'Роспись', print: 'Печать', design: 'Дизайн', sales: 'Продажи' }

export function usePulse(on) {
  const [p, setP] = useState(null)
  useEffect(() => { if (on) api('/head/pulse').then(setP, () => setP(false)) }, [on])
  return p
}

export function Pulse({ me, pulse, go }) {
  const p = pulse
  const [fin, setFin] = useState(null)
  useEffect(() => { api('/fin/summary?ym=' + ym()).then(setFin, e => setFin({ err: e.message })) }, [])
  if (p === null) return <div className="card muted">Загрузка…</div>
  if (p === false) return <div className="card muted">Пульт не загрузился. Обновите страницу.</div>
  const r = p.review
  const asks = [
    r.shifts && { k: 'review', t: `Смены на проверке: ${r.shifts}`, s: r.shifts_late ? `${r.shifts_late} дольше 24 ч` : 'в срок', hot: r.shifts_late },
    r.expenses && { k: 'review', t: `Расходы на проверке: ${r.expenses}`, s: `на ${money(r.expenses_sum)}` + (r.over_cap ? ` · ${r.over_cap} выше потолка цены` : ''), hot: r.expenses_late || r.over_cap },
    p.pending.length && { k: 'people', t: `Ждут роли: ${p.pending.length}`, s: p.pending.map(x => x.full_name).join(', '), hot: true },
    p.catalogs && { k: 'design', t: `Каталоги дизайна на утверждение: ${p.catalogs}`, s: 'утвердить или вернуть' },
    p.media && { k: 'prod', t: `Материал с объектов на утверждение: ${p.media}`, s: 'в «Продакшн» и рилс к оплате' },
  ].filter(Boolean)
  const name = (me.full_name || '').split(' ')[0]
  const active = p.team.reduce((n, t) => n + +t.active, 0)
  return <>
    <div className="card dark pulse-hero">
      <span className="muted small">{new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })}</span>
      <h1>{name ? `${name}, ` : ''}{asks.length ? 'ждёт решения' : 'всё решено'}</h1>
      <div className="pulse-kpi">
        <button className={asks.length ? 'hot' : ''} onClick={() => go('review')}><b>{r.shifts + r.expenses}</b><span>на проверке</span></button>
        <button className={p.pending.length ? 'hot' : ''} onClick={() => go('people')}><b>{p.pending.length}</b><span>новых людей</span></button>
        <button onClick={() => document.getElementById('pulse-today')?.scrollIntoView({ behavior: 'smooth' })}><b>{p.today.length}</b><span>смен сегодня</span></button>
      </div>
    </div>

    {asks.length > 0 && <div className="card"><h3>Ждёт вашего решения</h3>
      {asks.map((a, i) => <div key={i} className="qrow" onClick={() => go(a.k)}>
        <div className="qmain"><b>{a.t}</b><div className={'small ' + (a.hot ? 'why' : 'muted')}>{a.s}</div></div><span className="muted">›</span>
      </div>)}
    </div>}

    <div className="card"><div className="head"><h3>Деньги · {new Date().toLocaleDateString('ru-RU', { month: 'long' })}</h3>
      <button className="ghost mini" onClick={() => go('fin')}>Финансы</button></div>
      {!fin ? <p className="small muted">Считаю…</p> : fin.err ? <p className="small muted">{fin.err}</p> : <>
        <div className="kv">
          <div><span className="small muted">Выручка с НДС</span><b>{money(fin.revenue?.gross)}</b></div>
          <div><span className="small muted">Прибыль до ИПН</span><b className={fin.profit < 0 ? 'neg' : 'ok'}>{money(fin.profit)}</b></div>
          <div><span className="small muted">Пришло</span><b>{money(fin.cash?.in)}</b></div>
          <div><span className="small muted">Ушло</span><b>{money(fin.cash?.out)}</b></div>
        </div>
        {fin.warn?.length > 0 && <p className="small muted">{fin.warn[0]}</p>}
      </>}
    </div>

    <ViewAsCard />

    <div className="card" id="pulse-today"><h3>Сегодня на объектах</h3>
      {!p.today.length ? <p className="small muted">Смен сегодня пока нет.</p> : p.today.map(s => <div key={s.id} className="row">
        <div><b>{s.full_name}</b> <span className="small muted">{s.role_title}</span>
          <div className="small muted">{s.object_title} · {ZONE[s.zone_code] || s.zone_code}</div></div>
        <span className="small">{tm(s.started_at)}{s.ended_at ? '–' + tm(s.ended_at) : ''}</span>
      </div>)}
      <p className="small muted">За 7 дней: смен {(+p.week.approved) + (+p.week.rejected)} проверено ({p.week.rejected} отклонено), работали {p.week.people} чел.</p>
    </div>

    <div className="card"><div className="head"><h3>Команда · {active}</h3><button className="ghost mini" onClick={() => go('people')}>Команда</button></div>
      <div className="teamgrid">{p.team.filter(t => +t.active).map(t => <div key={t.code}><b>{t.active}</b><span className="small muted">{t.title}</span></div>)}</div>
      {!active && <p className="small muted">Ролей ещё никому не назначено.</p>}
    </div>

    <div className="card"><div className="head"><h3>Последние действия</h3><button className="ghost mini" onClick={() => go('journal')}>Журнал</button></div>
      {!p.feed.length ? <p className="small muted">Пока тихо.</p> : p.feed.map((f, i) => <div key={i} className="row">
        <div><b>{f.full_name}</b><div className="small muted">{(LABEL[f.action] || (() => f.action === 'register' ? 'Зарегистрировался' : f.action))(f)}</div></div>
        <span className="small muted">{ago(f.at)}</span>
      </div>)}
    </div>
  </>
}

// Посмотреть приложение глазами человека или роли. Только просмотр; вход и выход пишутся в журнал HEAD.
export function startViewAs(target) {
  return api('/view-as/start', { method: 'POST', body: { target: String(target) }, noView: true })
    .then(() => { setViewAs(String(target)); location.reload() })
}
export async function stopViewAs() {
  const t = viewAs()
  if (t.startsWith('test:')) await flush().catch(() => {})   // тест: отправить своё неотправленное от тестового сотрудника
  setViewAs('')
  return api('/view-as/stop', { method: 'POST', body: { target: t || '-' }, noView: true }).catch(() => {}).finally(() => location.reload())
}

export function ViewAsCard() {
  const [o, setO] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState('')
  useEffect(() => { api('/view-as/options', { noView: true }).then(setO, e => setErr(e.message)) }, [])
  const go = t => { setBusy(String(t)); startViewAs(t).catch(e => { setErr(e.message); setBusy('') }) }
  const people = (o?.people || []).filter(x => x.status !== 'blocked')
  return <div className="card viewas-card">
    <h3>Смотреть глазами сотрудника</h3>
    <p className="small muted">Приложение откроется так, как его видит человек: его меню, его сделки и смены. Только просмотр — ничего от его имени не отправится. Вход и выход — в вашем журнале.</p>
    {err && <p className="small why">{err}</p>}
    {!o ? <p className="small muted">Загрузка…</p> : <>
      {people.length ? people.map(x => <div key={x.id} className="row">
        <div><b>{x.full_name}</b> <span className="small muted">{x.role_title || (x.status === 'pending' ? 'ждёт роли' : '—')}</span></div>
        <button className="ghost mini" disabled={!!busy} onClick={() => go(x.id)}>{busy === String(x.id) ? 'Открываю…' : 'Смотреть'}</button>
      </div>) : <p className="small muted">В приложении пока никого, кроме вас.</p>}
      <p className="small muted" style={{ marginTop: 14 }}>Или роль целиком — меню и разделы роли на ваших данных (если человека ещё нет):</p>
      <div className="chips">{o.roles.map(r => <button key={r.code} className="ghost" disabled={!!busy} onClick={() => go('role:' + r.code)}>{r.title}</button>)}</div>
      {o.test && <div className="testas">
        <h3>Пройти как сотрудник · тест</h3>
        <p className="small muted">Здесь можно действовать: начать и закончить смену, загрузить фото, отправить расход. Всё идёт по-настоящему — в базу, на Диск в папку сделки, на проверку — от тестового сотрудника «Тест · роль». Только на test.</p>
        <div className="chips">{o.roles.map(r => <button key={r.code} disabled={!!busy} onClick={() => go('test:' + r.code)}>{r.title}</button>)}</div>
      </div>}
    </>}
  </div>
}

// Полоса сверху на всех экранах, пока HEAD смотрит чужими глазами: кто, что это только просмотр, выход одним нажатием.
export function ViewAsBar({ me, ROLE = {} }) {
  const v = me?._view_as
  const [msg, setMsg] = useState('')
  useEffect(() => {
    document.body.classList.toggle('viewas', !!v)
    const on = e => { setMsg(e.detail); setTimeout(() => setMsg(''), 3500) }
    window.addEventListener('artgame:ro', on)
    return () => window.removeEventListener('artgame:ro', on)
  }, [v])
  if (!v) return null
  return <div className="viewas-bar" role="status">
    <div className="vtext"><span className="eye">{v.kind === 'test' ? '🧪' : '👁'}</span><span>{v.kind === 'test' ? 'Тест: вы работаете как ' : 'Вы смотрите как '}<b>{me.full_name}</b>{v.kind === 'person' && me.role_code ? ` · ${ROLE[me.role_code] || me.role_code}` : ''}{v.note ? ` · ${v.note}` : ''}
      <i>{msg || (v.kind === 'test' ? 'всё сохраняется по-настоящему' : 'только просмотр')}</i></span></div>
    <button onClick={stopViewAs}>Вернуться к себе</button>
  </div>
}

import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { api } from './api.js'
import { ExpenseForm, Mine, Review, ShiftForm } from './work.jsx'
import { People } from './people.jsx'
import { Objects } from './objects.jsx'
import { Places, usePlaces } from './places.jsx'
import { DEAL_ROLES, Deals } from './deals.jsx'
import { Journal } from './journal.jsx'
import { Month } from './dealcard.jsx'
import { LeadCard, Leads, Today, useToday } from './crm.jsx'
import './tokens.css'

const ROLE = { support: 'Саппорт', artist: 'Художник', artist_pro: 'Художник Про', lead_artist: 'Главный художник',
  print_operator: 'Оператор настенного принтера', print_master: 'Мастер настенной печати', mop: 'МОП', mop_vip: 'VIP МОП',
  lead_designer: 'Главный дизайнер', designer_asst: 'Помощник дизайнера', head: 'HEAD' }
const ZONE = { mural: 'Роспись', print: 'Печать', design: 'Дизайн', sales: 'Продажи' }

function Register({ onDone }) {
  const tg = window.Telegram?.WebApp?.initDataUnsafe?.user
  const [name, setName] = useState([tg?.first_name, tg?.last_name].filter(Boolean).join(' '))
  const [phone, setPhone] = useState('')
  const [err, setErr] = useState('')
  const send = () => api('/register', { method: 'POST', body: { full_name: name, phone } }).then(onDone, e => setErr(e.message))
  return <div className="card">
    <h1>Добро пожаловать</h1>
    <p className="muted">Заполни имя, HEAD назначит тебе роль.</p>
    <input value={name} onChange={e => setName(e.target.value)} placeholder="Имя и фамилия" />
    <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="Телефон" inputMode="tel" />
    <button disabled={!name.trim()} onClick={send}>Отправить</button>
    {err && <p className="muted">{err}</p>}
  </div>
}

function App() {
  const [me, setMe] = useState(undefined)
  const [err, setErr] = useState('')
  useEffect(() => {
    window.Telegram?.WebApp?.ready()
    api('/me').then(setMe, e => e.status === 403 && e.message === 'not registered' ? setMe(null) : setErr(e.message))
  }, [])
  if (err) return <div className="wrap"><div className="card"><h1>ARTGAME</h1><p className="muted">Открой приложение из бота @artgame_team_bot. ({err})</p></div></div>
  if (me === undefined) return <div className="wrap muted">Загрузка…</div>
  if (me === null) return <div className="wrap"><Register onDone={setMe} /></div>
  if (me.status !== 'active') return <div className="wrap"><div className="card"><h1>{me.full_name}</h1>
    <p className="muted">{me.status === 'pending' ? 'Заявка у HEAD. Как только назначат роль, откроются разделы.' : 'Вход закрыт.'}</p></div></div>
  return <Main me={me} />
}

const CHECKERS = new Set(['head', 'lead_artist', 'print_master', 'lead_designer'])

function Main({ me }) {
  const places = usePlaces()
  const [tab, setTab] = useState(DEAL_ROLES.has(me.role_code) ? 'today' : 'shift')
  const [dealId, setDealId] = useState(null)
  const [leadId, setLeadId] = useState(null)
  const openDeal = id => { setDealId(id); setTab('deals') }
  const openLead = id => { setLeadId(id); setTab('leads') }
  const openMonth = () => setTab('month')
  const go = t => { if (t === 'deals') setDealId(null); if (t === 'leads') setLeadId(null); setTab(t) }
  const [toast, setToast] = useState('')
  const done = t => { setToast(t); setTab('mine'); setTimeout(() => setToast(''), 4000) }
  // Меню по роли (HEAD 05.11, «всё единым списком»): у МОП только продажи + место, у HEAD четыре главных и «Ещё».
  const sales = DEAL_ROLES.has(me.role_code)
  const t = useToday(sales)
  const counts = t ? { today: t.queue.hot.length + t.queue.today.length, leads: [...t.queue.hot, ...t.queue.today].filter(x => x.entity === 'lead').length } : {}
  const mop = ['mop', 'mop_vip'].includes(me.role_code)
  const tabs = [...(sales ? [['today', 'Сегодня'], ['leads', 'Лиды'], ['deals', 'Сделки'], ['month', 'Месяц']] : []),
    ...(places.length ? [['place', 'Место']] : []),
    ...(mop ? [] : [['shift', 'Смена'], ['expense', 'Расход'], ['objects', 'Объекты'], ['mine', 'Мои']]),
    ...(CHECKERS.has(me.role_code) ? [['review', 'Проверка']] : []),
    ...(me.role_code === 'head' ? [['journal', 'Журнал'], ['people', 'Команда']] : [])]
  if (tab === 'place') return <>
    <Places list={places} />
    <Nav tabs={tabs} tab={tab} setTab={go} counts={counts} />
  </>
  return <>
    <div className="wrap">
      {!['today', 'leads', 'deals', 'month'].includes(tab) && <div className="card"><h1>{me.full_name}</h1><span className="tag">{ROLE[me.role_code]}</span>{me.zones.map(z => <span key={z} className="tag">{ZONE[z]}</span>)}</div>}
      {toast && <div className="toast">{toast}</div>}
      {tab === 'people' ? <People ROLE={ROLE} ZONE={ZONE} /> : tab === 'deals' ? <Deals key={dealId || 0} initial={dealId} openMonth={openMonth} openPlace={() => { setDealId(null); setTab('place') }} /> :
        tab === 'leads' ? (leadId ? <LeadCard key={leadId} id={leadId} back={() => setLeadId(null)} openDeal={openDeal} /> : <Leads openLead={openLead} openMonth={openMonth} />) :
        tab === 'today' ? <Today openDeal={openDeal} openLead={openLead} openMonth={openMonth} /> : tab === 'month' ? <Month openDeal={openDeal} /> : tab === 'journal' ? <Journal me={me} /> : tab === 'objects' ? <Objects me={me} /> : !me.zones.length && tab !== 'review' ? <div className="card muted">HEAD ещё не назначил зону.</div> :
        tab === 'shift' ? <ShiftForm done={done} /> : tab === 'expense' ? <ExpenseForm done={done} /> : tab === 'mine' ? <Mine /> : <Review />}
    </div>
    <Nav tabs={tabs} tab={tab} setTab={go} counts={counts} />
  </>
}

const ICON = {
  today: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 5v5l3 2', leads: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-7 9a7 7 0 0 1 14 0',
  deals: 'M3 4h18l-7 8v6l-4 2v-8z', month: 'M4 20v-8m6 8V5m6 15v-5M3 20h18', place: 'M4 4h7v7H4zm9 0h7v7h-7zM4 13h7v7H4zm9 0h7v7h-7z',
  shift: 'M4 8h16v11H4zM9 8V5h6v3', expense: 'M3 6h18v12H3zm0 4h18', objects: 'M3 11l9-7 9 7v10H3zm6 10v-6h6v6',
  mine: 'M4 6h16M4 12h16M4 18h10', review: 'M20 6 9 17l-5-5', journal: 'M5 3h11a3 3 0 0 1 3 3v15H8a3 3 0 0 1-3-3zm4 5h6',
  people: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 20a7 7 0 0 1 14 0zm11 0a6 6 0 0 1 9 0',
  more: 'M5 12h.01M12 12h.01M19 12h.01' }
const Icon = ({ k }) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={ICON[k] || ICON.more} /></svg>

// Низ: не больше пяти кнопок одинаковой ширины, остальное — в листе «Ещё». Счётчики из очереди дня.
function Nav({ tabs, tab, setTab, counts = {} }) {
  const [more, setMore] = useState(false)
  const main = tabs.length > 5 ? tabs.slice(0, 4) : tabs
  const rest = tabs.length > 5 ? tabs.slice(4) : []
  const inRest = rest.find(([k]) => k === tab)
  return <>
    {more && <div className="sheet" onClick={() => setMore(false)}><div className="sheetbox" onClick={e => e.stopPropagation()}>
      {rest.map(([k, t]) => <button key={k} className={'ghost' + (tab === k ? ' on' : '')} onClick={() => { setTab(k); setMore(false) }}><Icon k={k} />{t}</button>)}
    </div></div>}
    <nav>
      {main.map(([k, t]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}><Icon k={k} />{t}{counts[k] ? <i className="cnt">{counts[k]}</i> : null}</button>)}
      {rest.length > 0 && <button className={inRest ? 'on' : ''} onClick={() => setMore(true)}><Icon k={inRest ? inRest[0] : 'more'} />{inRest ? inRest[1] : 'Ещё'}</button>}
    </nav>
  </>
}

createRoot(document.getElementById('root')).render(<App />)

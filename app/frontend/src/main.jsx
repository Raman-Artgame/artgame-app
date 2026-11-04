import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { api } from './api.js'
import { ExpenseForm, Mine, Review, ShiftForm } from './work.jsx'
import { People } from './people.jsx'
import { Objects } from './objects.jsx'
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
  const [tab, setTab] = useState('shift')
  const [toast, setToast] = useState('')
  const done = t => { setToast(t); setTab('mine'); setTimeout(() => setToast(''), 4000) }
  const tabs = [['shift', 'Смена'], ['expense', 'Расход'], ['objects', 'Объекты'], ['mine', 'Мои'], ...(CHECKERS.has(me.role_code) ? [['review', 'Проверка']] : []), ...(me.role_code === 'head' ? [['people', 'Команда']] : [])]
  return <>
    <div className="wrap">
      <div className="card"><h1>{me.full_name}</h1><span className="tag">{ROLE[me.role_code]}</span>{me.zones.map(z => <span key={z} className="tag">{ZONE[z]}</span>)}</div>
      {toast && <div className="toast">{toast}</div>}
      {tab === 'people' ? <People ROLE={ROLE} ZONE={ZONE} /> : tab === 'objects' ? <Objects me={me} /> : !me.zones.length && tab !== 'review' ? <div className="card muted">HEAD ещё не назначил зону.</div> :
        tab === 'shift' ? <ShiftForm done={done} /> : tab === 'expense' ? <ExpenseForm done={done} /> : tab === 'mine' ? <Mine /> : <Review />}
    </div>
    <nav>{tabs.map(([k, t]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{t}</button>)}</nav>
  </>
}

createRoot(document.getElementById('root')).render(<App />)

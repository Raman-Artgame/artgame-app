import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { api, inTelegram, setViewAs, setWebToken, webToken } from './api.js'
import { Login } from './login.jsx'
import { ExpenseForm, Mine, Review, ShiftForm } from './work.jsx'
import { MyIssued, People } from './people.jsx'
import { Places, usePlaces } from './places.jsx'
import { DEAL_ROLES, Deals } from './deals.jsx'
import { Journal } from './journal.jsx'
import { Month } from './dealcard.jsx'
import { Projects } from './projects.jsx'
import { LeadCard, Leads, Today, useToday } from './crm.jsx'
import { Finance, MyPay, StockSpend } from './finance.jsx'
import { Kit } from './kit.jsx'
import { Production } from './production.jsx'
import { Design } from './design.jsx'
import { DUTIES, GROW } from './duties.js'
import { Pulse, ViewAsBar, ViewAsCard, usePulse } from './head.jsx'
import './tokens.css'

const ROLE = { support: 'Саппорт', artist: 'Художник', artist_pro: 'Художник Про', lead_artist: 'Главный художник',
  print_operator: 'Оператор настенного принтера', print_master: 'Мастер настенной печати', mop: 'МОП', mop_vip: 'VIP МОП',
  lead_designer: 'Главный дизайнер', designer_asst: 'Помощник дизайнера', carpenter: 'Мастер-плотник', head: 'HEAD' }
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
  const web = !inTelegram()
  const [login, setLogin] = useState(web && !webToken())
  const load = () => { setErr(''); setMe(undefined); api('/me').then(setMe, e => e.status === 401 && web ? setLogin(true) : e.status === 403 && e.message === 'not registered' ? setMe(null) : setErr(e.message)) }
  useEffect(() => {
    window.Telegram?.WebApp?.ready()
    try { window.Telegram?.WebApp?.setHeaderColor?.('#F1F0EC'); window.Telegram?.WebApp?.setBackgroundColor?.('#F1F0EC') } catch { /* старый клиент */ }
    if (web) document.body.classList.add('web')
    const out = () => setLogin(true)
    window.addEventListener('artgame:logout', out)
    if (!login) load()
    return () => window.removeEventListener('artgame:logout', out)
  }, [])
  if (login) return <div className="wrap"><Login onDone={() => { setLogin(false); load() }} /></div>
  if (err) return <div className="wrap"><div className="card"><h1>ARTGAME</h1><p className="muted">Открой приложение из бота @artgame_team_bot. ({err})</p></div></div>
  if (me === undefined) return <div className="wrap muted">Загрузка…</div>
  if (me === null) return <div className="wrap"><Register onDone={setMe} /></div>
  if (me.status !== 'active') return <><ViewAsBar me={me} ROLE={ROLE} /><div className="wrap"><div className="card"><h1>{me.full_name}</h1>
    <p className="muted">{me.status === 'pending' ? 'Заявка у HEAD. Как только назначат роль, откроются разделы.' : 'Вход закрыт.'}</p></div></div></>
  return <><ViewAsBar me={me} ROLE={ROLE} />
    <Main me={me} web={web} logout={() => { api('/logout', { method: 'POST', noView: true }).catch(() => {}); setWebToken(''); setViewAs(''); setLogin(true) }} /></>
}

const CHECKERS = new Set(['head', 'lead_artist', 'artist_pro', 'print_master', 'lead_designer'])
// Кабинеты команды (HEAD 07.11, правки 08.11). Художники: Смена · Расход · Проекты · Учёба · Мои; Главному и Про ещё Проверка,
// Продакшн, Сбор. «Объекты» влиты в «Проекты» (карточка проекта: эскизы, фото, продакшн). Дизайнеры: Дизайн · Проекты · Учёба · Мои · Расход.
// В «Учёбе» скрыто то, что ещё в разработке: «Оплата», «Рост и экзамены»; у дизайна — «Проекты» и «Передача» места.
const ART = new Set(['support', 'artist', 'lead_artist', 'artist_pro'])
const SENIOR = new Set(['lead_artist', 'artist_pro'])
const DZ = new Set(['lead_designer', 'designer_asst'])
const KIT = new Set(['lead_artist', 'artist_pro', 'print_master', 'head'])
// HEAD 08.11: «Продакшн» — у Главного, Про и Мастера настенной печати (HEAD утверждает); склад — только у них же (и плотника).
const PROD = new Set(['lead_artist', 'artist_pro', 'print_master', 'head'])
const STOCK = new Set(['lead_artist', 'artist_pro', 'print_master', 'carpenter'])
const PRINT = new Set(['print_operator', 'print_master'])
const STUDY = {
  // HEAD 08.11: в «Учёбе» — База знаний (учебник), Тест, Клиентам; «Выезд» переехал в «Смену» подсказками,
  // «Куратор/ГИП», «Главный художник», «Рост», «Оплата» скрыты. Рядом свои чипы: «ТБ» и «Правила игры».
  art: () => ({ home: 'ucheb', hide: ['trip', 'gip', 'chief', 'grow', 'pay'], sections: [['ucheb', 'Учебник'], ['test', 'Тест'], ['mat', 'Клиентам']] }),
  // печать — так же: Учебник, Тест, Фотозадание, Клиентам; «Запуск» и «Сборы» — в «Смене» и «Сборе», «Экзамен» со ставками — скрыт
  print: () => ({ home: 'ucheb', hide: ['start', 'kit', 'exam'], sections: [['ucheb', 'Учебник'], ['test', 'Тест'], ['foto', 'Фотозадание'], ['mat', 'Клиентам']] }),
  dz: () => ({ home: 'learn', hide: ['board', 'handoff'] }),
}
const PLAIN = new Set(['today', 'leads', 'deals', 'projects', 'month'])

// Единое рабочее поле МОП (HEAD 06.11): вся работа по клиенту — в карточке сделки; «Место» МОП стало «Учёбой»
// (учебник, тест, правила игры); общая вкладка «Проекты» — кто где и сколько дней осталось.
function Main({ me, web, logout }) {
  const places = usePlaces()
  const mopPlace = places.find(p => p.code === 'mop')
  const other = places.filter(p => p.code !== 'mop')
  const role = me.role_code
  const art = ART.has(role), dz = DZ.has(role), prn = PRINT.has(role), cab = art || dz || prn
  const own = art ? 'art' : prn ? 'print' : 'dz'   // своё место: Главному доступно и «Печать», но в «Учёбе» — только своё
  const studyList = cab ? places.filter(p => p.code === own) : []
  const isHead = role === 'head'
  const [tab, setTab] = useState(isHead ? 'home' : DEAL_ROLES.has(role) ? 'today' : role === 'carpenter' ? 'stock' : dz ? 'design' : 'shift')
  const [dealId, setDealId] = useState(null)
  const [leadId, setLeadId] = useState(null)
  const openDeal = id => { setDealId(id); setTab('deals') }
  const openLead = id => { setLeadId(id); setTab('leads') }
  const openMonth = () => setTab('month')
  const go = t => { if (t === 'deals') setDealId(null); if (t === 'leads') setLeadId(null); setTab(t) }
  const [toast, setToast] = useState('')
  const done = t => { setToast(t); setTab('mine'); setTimeout(() => setToast(''), 4000) }
  useEffect(() => {   // офлайн-очередь: сервер не принял запись — сказать сразу, а не терять молча
    const on = e => { setToast('Не отправлено: ' + e.detail); setTimeout(() => setToast(''), 8000) }
    window.addEventListener('artgame:dropped', on)
    return () => window.removeEventListener('artgame:dropped', on)
  }, [])
  const sales = DEAL_ROLES.has(me.role_code)
  const t = useToday(sales)
  const pulse = usePulse(isHead)
  const counts = { ...(t ? { today: t.queue.hot.length + t.queue.today.length, leads: [...t.queue.hot, ...t.queue.today].filter(x => x.entity === 'lead').length } : {}),
    ...(pulse ? { review: +pulse.review.shifts + +pulse.review.expenses, people: pulse.pending.length } : {}) }
  const mop = ['mop', 'mop_vip'].includes(me.role_code)
  const carp = me.role_code === 'carpenter'
  // HEAD 08.11 (вечер): у художников и печати всё внизу одной лентой, в таком порядке — Сбор · Смена · Расход · Продакшн ·
  // Проверка · Проекты · Учёба · Кабинет (у кого что есть). Склад — внутри «Расхода». «Мои» → «Кабинет».
  const worker = art || PRINT.has(role)
  const tabs = worker ? [...(KIT.has(role) ? [['kit', 'Сбор']] : []), ['shift', 'Смена'], ['expense', 'Расход'],
    ...(PROD.has(role) ? [['prod', 'Продакшн']] : []), ...(CHECKERS.has(role) ? [['review', 'Проверка']] : []), ['projects', 'Проекты'],
    ['study', 'Учёба'], ['mine', 'Кабинет']] :
    dz ? [['design', 'Дизайн'], ['projects', 'Проекты'], ...(CHECKERS.has(role) ? [['review', 'Проверка']] : []), ['study', 'Учёба'], ['mine', 'Кабинет'], ['expense', 'Расход']] :
   [...(sales ? [['today', 'Сегодня'], ['leads', 'Лиды'], ['deals', 'Сделки'], ['projects', 'Проекты'], ['month', 'Месяц']] : []),
    ...(mopPlace ? [['study', 'Учёба']] : []),
    ...(other.length ? [['place', 'Место']] : []),
    ...(mop || carp ? [] : [['shift', 'Смена'], ['expense', 'Расход']]),
    ...(STOCK.has(role) ? [['stock', 'Склад']] : []), ['mine', 'Кабинет'],
    ...(!sales ? [['projects', 'Проекты']] : []),
    ...(PROD.has(role) ? [['prod', 'Продакшн']] : []),
    ...(CHECKERS.has(me.role_code) ? [['review', 'Проверка']] : []),
    ...(KIT.has(role) ? [['kit', 'Сбор']] : []),
    ...(role === 'head' ? [['design', 'Дизайн'], ['fin', 'Финансы'], ['journal', 'Журнал'], ['people', 'Команда']] : [])]
  // Кабинет HEAD (08.11): Пульт · Проверка · Сделки · Финансы · Команда, остальное — в «Ещё», там же «Смотреть как».
  const HEAD_FIRST = ['review', 'deals', 'fin', 'people']
  const menu = isHead ? [['home', 'Пульт'], ...HEAD_FIRST.map(k => tabs.find(x => x[0] === k)).filter(Boolean),
    ...tabs.filter(x => !HEAD_FIRST.includes(x[0])), ['viewas', 'Смотреть как']] : tabs
  const duty = DUTIES[role]
  if (tab === 'place' || tab === 'study') return <>
    {cab ? <Places key={tab} list={studyList} mode="study" opts={Object.fromEntries(studyList.map(p => [p.code, STUDY[p.code](role)]))}
      extra={[(art || prn) && { code: 'tb', title: 'ТБ', render: () => <Safety print={prn} /> },
        duty && { code: 'duty', title: 'Правила игры', render: () => <Duty d={duty} g={GROW[role]} /> }].filter(Boolean)} /> :
    <Places key={tab} list={tab === 'study' ? [mopPlace] : other} mode={tab === 'study' ? 'study' : ''} />}
    <Nav tabs={menu} tab={tab} setTab={go} counts={counts} scroll />
  </>
  return <>
    <div className="wrap">
      {web && <div className="webbar"><b>ARTGAME</b><span className="muted small">{me.full_name}</span><button className="ghost mini" onClick={logout}>Выйти</button></div>}
      {!PLAIN.has(tab) && tab !== 'home' && <div className="card"><h1>{me.full_name}</h1><span className="tag">{ROLE[me.role_code]}</span>{me.zones.map(z => <span key={z} className="tag">{ZONE[z]}</span>)}</div>}
      {toast && <div className="toast">{toast}</div>}
      {tab === 'home' ? <Pulse me={me} pulse={pulse} go={go} /> : tab === 'viewas' ? <ViewAsCard /> :
        tab === 'people' ? <People ROLE={ROLE} ZONE={ZONE} /> : tab === 'deals' ? <Deals key={dealId || 0} initial={dealId} place={mopPlace} /> :
        tab === 'leads' ? (leadId ? <LeadCard key={leadId} id={leadId} back={() => setLeadId(null)} openDeal={openDeal} /> : <Leads openLead={openLead} openMonth={openMonth} />) :
        tab === 'today' ? <Today openDeal={openDeal} openLead={openLead} openMonth={openMonth} /> : tab === 'month' ? <Month openDeal={openDeal} /> :
        tab === 'projects' ? <Projects openDeal={sales ? openDeal : null} me={me} /> : tab === 'journal' ? <Journal me={me} /> : tab === 'prod' ? <Production me={me} /> :
        tab === 'fin' ? <Finance /> : tab === 'stock' ? <StockSpend /> : tab === 'kit' ? <Kit /> : tab === 'design' ? <Design me={me} /> :
        tab === 'expense' && STOCK.has(role) && me.zones.length ? <ExpenseTab done={done} /> :
        tab === 'mine' && (mop || carp || !me.zones.length) ? <><MyPay /><MyIssued />{duty && <DutyFold d={duty} />}</> : !me.zones.length && tab !== 'review' ? <div className="card muted">HEAD ещё не назначил зону.</div> :
        tab === 'shift' ? <ShiftForm done={done} /> : tab === 'expense' ? <ExpenseForm done={done} /> : tab === 'mine' ? <><MyPay /><MyIssued />{duty && <DutyFold d={duty} />}<Mine /></> : <Review />}
    </div>
    <Nav tabs={menu} tab={tab} setTab={go} counts={counts} scroll />
  </>
}

// Расход художника и дизайнера: на объект с чеком или закупка на склад (HEAD 06.11 — склад внутри «Расхода»).
function ExpenseTab({ done }) {
  const [v, setV] = useState('obj')
  return <>
    <div className="segf"><button className={v === 'obj' ? 'on' : ''} onClick={() => setV('obj')}>На объект</button>
      <button className={v === 'stock' ? 'on' : ''} onClick={() => setV('stock')}>Закупка на склад</button></div>
    {v === 'obj' ? <ExpenseForm done={done} /> : <StockSpend />}
  </>
}

// «Как стать художником» (HEAD 08.11) — для саппорта: что нужно уметь, как проходит экзамен, кто принимает.
function Grow({ g }) {
  return <div className="card duty">
    <span className="tag">{g.step}</span><h2>{g.title}</h2><p>{g.about}</p>
    <h3>Что нужно уметь</h3>{g.check.map((x, i) => <div key={i} className="growrow"><span>{i + 1}</span>{x}</div>)}
    <h3>Экзамен</h3>{g.exam.map(([t, how, ok]) => <div key={t} className="growexam"><b>{t}</b><span className="small">{how}</span><span className="small muted">Зачёт: {ok}</span></div>)}
    <p className="small muted">{g.who}</p><p className="small muted">Источник: {g.src}</p>
  </div>
}

// «Правила игры» (HEAD 08.11 — вместо «Должностной»): роль, кому подчиняешься, что делаешь; ниже — как вырасти на ступень.
// «Правила игры» в «Кабинете» у всех (HEAD 08.11): свёрнуто одной карточкой, раскрывается целиком.
function DutyFold({ d }) {
  const [open, setOpen] = useState(false)
  return <div className="card dutyfold">
    <div className="head" onClick={() => setOpen(!open)} style={{ cursor: 'pointer' }}>
      <div><span className="tag">Правила игры</span><h3>{d.title}</h3><p className="small muted">{d.about}</p></div>
      <button className="ghost mini">{open ? 'Свернуть' : 'Открыть'}</button></div>
    {open && <div className="dutybody"><Duty d={d} /></div>}
  </div>
}

function Duty({ d, g }) {
  return <div className="wrap"><div className="card duty">
    <span className="tag">{d.step}</span><h2>Правила игры · {d.title}</h2><p>{d.about}</p><p className="small muted">{d.boss}</p>
    <h3>Что ты делаешь</h3><ul>{d.duty.map((x, i) => <li key={i}>{x}</li>)}</ul>
    <p className="small muted">Ставки — в «Кабинете».</p>
  </div>
  {d.skills && <div className="card duty"><h3>Какой ты: команда, управление, мастерство</h3>
    {d.skills.map(([t, x]) => <div key={t} className="skill"><b>{t}</b><p className="small">{x}</p></div>)}</div>}
  {d.rules && <div className="card duty"><h3>Правила</h3>
    {d.rules.map(([t, x]) => <div key={t} className="skill"><b>{t}</b><p className="small">{x}</p></div>)}</div>}
  {d.next && <div className="card duty"><h3>Куда дальше</h3><p className="small">{d.next}</p></div>}
  {g && <Grow g={g} />}</div>
}

// ТБ (HEAD 08.11): главное по безопасности с цифрами из «Значений» (safety.*). Полная глава — «База знаний», глава 10.
function Safety({ print }) {
  const [v, setV] = useState(null)
  useEffect(() => { api('/work/dict').then(d => setV(d.safety || {}), () => setV({})) }, [])
  const n = (k, d) => String(v?.[k] ?? d).replace('.', ',')
  if (!v) return <div className="wrap"><div className="card muted">Загрузка…</div></div>
  const rows = [[`${n('safety.harness_from', '1,8')} м`, 'С этой высоты без ограждения — только со страховкой. Анкер выше плеч, не к трубам и перилам.'],
    [`${n('safety.anchor_from', 4)} м`, 'Вышки и леса выше — опоры и анкер к стене, колёса на тормозах.'],
    [`${n('safety.wind.tower_stop', 12)} м/с`, 'Ветер сильнее — на вышке не работаем.'],
    [`${n('safety.wind.move_stop', 10)} м/с`, 'Ветер сильнее — вышку не передвигаем; люлька и автовышка — стоп.'],
    [`${n('safety.rescue_min', 10)}–${n('safety.rescue_max', 15)} мин`, 'За столько эвакуировать человека, повисшего в привязи. Сразу — скорая.'],
    ['1 + 1', 'Один на высоте не работает: внизу всегда второй.'],
    ['Очки', 'Всегда. Респиратор — распыление, аэрозоль, шлифовка.'],
    ['Стоп', 'Дым, искрение, вибрация, повреждённый кабель — остановить, отключить, сообщить ' + (print ? 'Мастеру печати' : 'Главному') + '. Самим не чинить.']]
  return <div className="wrap"><div className="card tbcard">
    <span className="tag">Техника безопасности</span><h2>ТБ на объекте</h2>
    <p className="small muted">Никто не работает на оборудовании без обучения и сданной ТБ. Допуск даёт {print ? 'Мастер настенной печати (принтер), к вышкам и инструменту — Главный художник или Художник-Про' : 'Главный художник или Художник-Про'}.</p>
    {rows.map(([k, t]) => <div key={k} className="tbrow"><b>{k}</b><span>{t}</span></div>)}
    <p className="small muted">Подробно — «Учебник», глава {print ? 11 : 10} «Техника безопасности». Цифры — из «Значений».</p>
  </div></div>
}

const ICON = {
  today: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 5v5l3 2', leads: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm-7 9a7 7 0 0 1 14 0',
  deals: 'M3 4h18l-7 8v6l-4 2v-8z', month: 'M4 20v-8m6 8V5m6 15v-5M3 20h18', place: 'M4 4h7v7H4zm9 0h7v7h-7zM4 13h7v7H4zm9 0h7v7h-7z',
  projects: 'M3 21V8l9-5 9 5v13M9 21v-7h6v7M3 12h18', study: 'M4 5h7a2 2 0 0 1 2 2v13H6a2 2 0 0 1-2-2zm9 2a2 2 0 0 1 2-2h5v13a2 2 0 0 1-2 2h-5',
  shift: 'M4 8h16v11H4zM9 8V5h6v3', expense: 'M3 6h18v12H3zm0 4h18', objects: 'M3 11l9-7 9 7v10H3zm6 10v-6h6v6',
  mine: 'M3 5h18v14H3zM8 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4zm-3 5a3 3 0 0 1 6 0M14 9h4M14 13h4',
  // «Продакшн» (HEAD 08.11): камера с кнопкой записи
  prod: 'M3 7h12v10H3zm12 3.5 6-3.5v10l-6-3.5M7 10.5l3 1.5-3 1.5z', review: 'M20 6 9 17l-5-5', journal: 'M5 3h11a3 3 0 0 1 3 3v15H8a3 3 0 0 1-3-3zm4 5h6',
  fin: 'M12 3v18M16 7H10a3 3 0 0 0 0 6h4a3 3 0 0 1 0 6H7', stock: 'M3 7l9-4 9 4v10l-9 4-9-4zm0 0 9 4 9-4M12 11v10',
  people: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm7 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM2 20a7 7 0 0 1 14 0zm11 0a6 6 0 0 1 9 0',
  kit: 'M9 4h6l1 3h4v13H4V7h4zm-1 8 3 3 5-5', design: 'M12 3a9 9 0 1 0 0 18c1 0 1.5-.7 1.5-1.5 0-1-.8-1.4-.8-2.3 0-.9.7-1.6 1.6-1.6H17a4 4 0 0 0 4-4c0-4.7-4-8.6-9-8.6zM7.5 12h.01M10 7.5h.01M15 7.5h.01',
  home: 'M4 13a8 8 0 1 1 16 0M12 13l4-4M4 17h16',
  viewas: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  more: 'M5 12h.01M12 12h.01M19 12h.01' }
const Icon = ({ k }) => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={ICON[k] || ICON.more} /></svg>
const MAX = 6   // кнопок в меню без листа «Ещё»

// scroll (HEAD 08.11, у всех): все кнопки внизу одной лентой без «Ещё», лента листается пальцем; открытая вкладка — в поле зрения.
function Nav({ tabs, tab, setTab, counts = {}, scroll }) {
  const [more, setMore] = useState(false)
  const fold = !scroll && tabs.length > MAX
  const main = fold ? tabs.slice(0, MAX - 1) : tabs
  const rest = fold ? tabs.slice(MAX - 1) : []
  const inRest = rest.find(([k]) => k === tab)
  return <>
    {more && <div className="sheet" onClick={() => setMore(false)}><div className="sheetbox" onClick={e => e.stopPropagation()}>
      {rest.map(([k, t]) => <button key={k} className={'ghost' + (tab === k ? ' on' : '')} onClick={() => { setTab(k); setMore(false) }}><Icon k={k} />{t}</button>)}
    </div></div>}
    <nav className={scroll && tabs.length > MAX ? 'scroll' : ''}>
      {main.map(([k, t]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}
        ref={el => { if (el && tab === k && scroll) el.scrollIntoView?.({ block: 'nearest', inline: 'nearest' }) }}><Icon k={k} />{t}{counts[k] ? <i className="cnt" aria-hidden="true">{counts[k]}</i> : null}</button>)}
      {rest.length > 0 && <button className={inRest ? 'on' : ''} onClick={() => setMore(true)}><Icon k={inRest ? inRest[0] : 'more'} />{inRest ? inRest[1] : 'Ещё'}</button>}
    </nav>
  </>
}

createRoot(document.getElementById('root')).render(<App />)

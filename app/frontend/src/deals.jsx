import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { DealCard } from './dealcard.jsx'
import { Skeleton, ageDays, cleanTitle, loadToday, money, useToday } from './crm.jsx'

export const DEAL_ROLES = new Set(['mop', 'mop_vip', 'head'])
const IDLE = 3   // дней без движения — красный бейдж (как mop.today.idle_days)

// Сделки (HEAD 05.11 → 26.11): было «лента стадий + список», теперь канбан основной воронки; воронка «Дизайн» — прежним списком.
// По умолчанию открыта стадия, где есть застрявшие сделки. Вся работа — в карточке сделки (HEAD 06.11: единое рабочее поле).
// Канбан (HEAD 26.11 «нужен нормальный канбан как в Битриксе»): колонки стадий листаются вбок, карточку тянем в другую
// стадию (замок карточки проверяет сервер), сумма крупно, итог по колонке. Продажи и «В работе» (договор → выполнение →
// закрывающие) — отдельными досками. Напоминания «кто что ждёт» — из той же очереди, что «Сегодня» (/bx/today):
// красное — действие за МОП, жёлтое — ждём клиента, серое — стоит, зелёное — пора в производство.
const SALES = ['NEW', 'PREPARATION', 'UC_VZFPUP', 'UC_YV66BV', 'UC_1EXUAC', 'UC_VCP4VO']
const WORK = ['FINAL_INVOICE', 'UC_AV00QK', 'UC_BMKDS4']
const POSTPONED = 'UC_VCP4VO'
const TONES = [['hot', 'Ответить сейчас', 'за вами'], ['go', 'Пора в производство', 'эскиз утверждён'], ['wait', 'Ждём клиента', 'напомнить, если молчит'], ['idle', 'Стоят', 'без движения']]
const RANK = { hot: 4, go: 3, wait: 2, idle: 1 }
const cap = t => t ? t[0].toUpperCase() + t.slice(1) : ''
const ddmm = s => s ? s.slice(8, 10) + '.' + s.slice(5, 7) : ''
const daysTo = s => s ? Math.round((new Date(s + 'T00:00:00') - new Date(new Date().toDateString())) / 864e5) : null
// доска «В работе» (HEAD 26.11): сколько оплачено и сколько осталось, кто куратор ГИП, когда сдача
function WorkLine({ d }) {
  const pct = d.sum ? Math.min(100, Math.round(100 * (d.paid || 0) / d.sum)) : 0, left = daysTo(d.end)
  return <div className="kwork">
    <div className="kpay"><i style={{ width: pct + '%' }} /></div>
    <div className="kpayt">{d.paid ? <span>Оплачено <b>{money(d.paid)}</b></span> : <span className="warn">Оплат ещё нет</span>}
      {d.debt > 0 ? <span>долг <b>{money(d.debt)}</b></span> : d.paid ? <span className="ok">оплачено полностью</span> : null}</div>
    <div className="kmeta"><span>{d.gip ? 'ГИП ' + d.gip.split(' ')[0] : <em>ГИП не назначен</em>}</span>
      {d.end ? <span className={left < 0 ? 'late' : left <= 3 ? 'soon' : ''}>сдача {ddmm(d.end)}{left < 0 ? ` · просрочено ${-left} дн.` : left <= 3 ? ` · через ${left} дн.` : ''}</span>
        : <em>срок сдачи не указан</em>}</div>
  </div>
}
const mln = n => n >= 1e6 ? (Math.round(n / 1e5) / 10).toLocaleString('ru-RU') + ' млн ₸' : money(n)
export function reminders(t) {
  const m = {}
  for (const [b, items] of Object.entries(t?.queue || {})) for (const x of items) {
    const id = x.entity === 'deal' ? x.id : x.entity === 'task' ? x.deal : null
    if (!id) continue
    const tone = x.action === 'production' ? 'go' : b === 'hot' ? 'hot' : b === 'today' || x.wait || x.entity === 'task' ? 'wait' : 'idle'
    if (!m[id] || RANK[tone] > RANK[m[id].tone]) m[id] = { tone, text: cap(x.why) }
  }
  return m
}

export function Deals({ initial, place }) {
  const [card, setCard] = useState(initial || null)
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [cat, setCat] = useState(0)        // воронка: 0 Продажи (основная), 13 Дизайн
  const [mgr, setMgr] = useState(0)        // HEAD: фильтр по менеджеру
  const [st, setSt] = useState(null)       // стадия: id | 'all' | null — сама выберет
  const [board, setBoard] = useState('sales')   // sales | work — доски основной воронки
  const [tone, setTone] = useState('')            // фильтр по напоминанию
  const [stages, setStages] = useState([])
  const [moved, setMoved] = useState({})          // id → стадия, пока сервер не подтвердил перенос
  const [over, setOver] = useState('')
  const [msg, setMsg] = useState(null)            // {text, id}
  const drag = useRef(null)
  const today = useToday()
  const load = fresh => { setBusy(true); setErr(''); if (fresh) loadToday(true).catch(() => {})
    return api(`/bx/deals${fresh ? '?fresh=1' : ''}`).then(setData, e => setErr(e.message)).finally(() => setBusy(false)) }
  useEffect(() => { load(false); api('/bx/stages').then(setStages, () => {}) }, [])
  if (card) return <DealCard id={card} back={() => { setCard(null); setMoved({}); load(true) }} place={place} />
  if (err) return <div className="card"><h2>Сделки</h2><p className="muted">{err}</p></div>
  if (!data) return <Skeleton n={4} />
  const s = q.trim().toLowerCase()
  const mine = data.deals.filter(d => !mgr || d.manager_id === mgr)
  const list = mine.filter(d => d.category === cat && (!s || String(d.id).includes(s) || d.title.toLowerCase().includes(s) || (d.manager || '').toLowerCase().includes(s)))
  const total = list.reduce((a, d) => a + (d.sum || 0), 0)
  const funnels = Object.entries(data.funnels || { 0: 'Продажи', 13: 'Дизайн' }).map(([k, name]) => [+k, name, mine.filter(d => d.category === +k).length])
  const rem = reminders(today)
  const stageOf = d => moved[d.id] || d.stage
  const head = <div className="card"><div className="head"><h2>{data.all ? 'Сделки' : 'Мои сделки'} <span className="kbtotal">{money(total)}</span> <span className="muted small">{list.length}</span></h2>
      <button className="ghost mini" disabled={busy} onClick={() => load(true)}>{busy ? '…' : 'Обновить'}</button></div>
    <div className="segf">{funnels.map(([k, name, n]) => k === 0
      ? [['sales', 'Продажи', SALES], ['work', 'В работе', WORK]].map(([b, bn, ids]) => <button key={b} className={cat === 0 && board === b ? 'on' : ''}
        onClick={() => { setCat(0); setBoard(b); setTone('') }}>{bn} <span>{mine.filter(d => d.category === 0 && ids.includes(stageOf(d))).length}</span></button>)
      : <button key={k} className={cat === k ? 'on' : ''} onClick={() => { setCat(k); setSt(null) }}>{name} <span>{n}</span></button>)}</div>
    {data.all && data.managers.length > 1 && <div className="chips sub"><button className={!mgr ? 'on' : ''} onClick={() => setMgr(0)}>Все</button>
      {data.managers.map(([id, name]) => <button key={id} className={mgr === id ? 'on' : ''} onClick={() => setMgr(id)}>{name.split(' ')[0]}</button>)}</div>}
    <input value={q} onChange={e => setQ(e.target.value)} placeholder="Номер, название или менеджер" />
  </div>
  if (cat !== 0) return <>{head}<FunnelList list={list} all={data.all} st={st} setSt={setSt} s={s} open={setCard} /></>

  // ---- канбан основной воронки ----
  const known = id => !stages.length || stages.some(x => x.id === id)   // стадии, которых нет в Битриксе, не рисуем
  const ids = (s ? [...SALES, ...WORK] : board === 'sales' ? SALES : WORK).filter(known)   // поиск — по обеим доскам
  const name = id => stages.find(x => x.id === id)?.name || list.find(d => d.stage === id)?.stage_name || id
  const onBoard = list.filter(d => ids.includes(stageOf(d)))
  const counts = Object.fromEntries(TONES.map(([k]) => [k, onBoard.filter(d => rem[d.id]?.tone === k).length]))
  const shown = tone ? onBoard.filter(d => rem[d.id]?.tone === tone) : onBoard
  const cols = ids.map(id => { const items = shown.filter(d => stageOf(d) === id)
    return { id, name: name(id), items: items.sort((a, b) => (RANK[rem[b.id]?.tone] || 0) - (RANK[rem[a.id]?.tone] || 0)), sum: items.reduce((a, d) => a + (d.sum || 0), 0), debt: items.reduce((a, d) => a + (d.debt || 0), 0) } })
  const say = (text, id) => { setMsg({ text, id }); setTimeout(() => setMsg(m => (m && m.text === text ? null : m)), 9000) }
  const drop = to => {
    const d = list.find(x => x.id === drag.current); drag.current = null; setOver('')
    if (!d || stageOf(d) === to) return
    if (to === POSTPONED) return say('«Отложено» — с датой возврата: откройте сделку → «Ещё действия» → «Стадия».', d.id)
    const was = stageOf(d)   // откат — туда, где карточка стояла (в т. ч. после прошлого переноса)
    setMoved(m => ({ ...m, [d.id]: to }))
    api(`/bx/deals/${d.id}/stage`, { method: 'POST', body: { stage: to } })
      .then(() => { say(`№ ${d.id} → «${name(to)}»`); loadToday(true).catch(() => {}) },
        e => { setMoved(m => ({ ...m, [d.id]: was })); say(`№ ${d.id} не перенесена: ${e.message}`, d.id) })
  }
  const canDrag = board === 'sales' && !s
  const kcard = d => { const r = rem[d.id], age = ageDays(d.active || d.modified)
    return <div key={d.id} className={'kc' + (r?.tone === 'hot' ? ' hotc' : '')} draggable={canDrag}
      onDragStart={e => { drag.current = d.id; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', String(d.id)) }}
      onDragEnd={() => setOver('')} onClick={() => setCard(d.id)}>
      <div className="kn">№ {d.id}{d.city ? ` · ${d.city}` : ''}</div>
      <div className="kt">{cleanTitle(d.title, d.id)}</div>
      <div className={'ks' + (d.sum ? '' : ' nosum')}>{d.sum ? money(d.sum) : 'сумма не указана'}</div>
      {r ? <span className={'kr ' + r.tone}>{r.text}</span> : age >= IDLE ? <span className="kr idle">Без движения {age} дн.</span> : null}
      {WORK.includes(stageOf(d)) ? <WorkLine d={d} /> : null}
      <div className="kw">{[d.kind, data.all ? d.manager.split(' ')[0] : ''].filter(Boolean).join(' · ') || (d.area ? d.area + ' м²' : '')}</div>
    </div> }
  return <>
    {head}
    <div className="kbnow">{TONES.filter(([k]) => counts[k] || k !== 'go').map(([k, t, sub]) => <button key={k} className={'kbcount ' + k + (tone === k ? ' on' : '')}
      onClick={() => setTone(tone === k ? '' : k)}><span>{t}</span><b>{counts[k]}</b><i>{tone === k ? 'показаны только они · снять' : sub}</i></button>)}</div>
    {msg && <div className="toast kbmsg">{msg.text}{msg.id ? <button className="ghost mini" onClick={() => setCard(msg.id)}>Открыть сделку</button> : null}</div>}
    <div className="kb">{cols.map(c => <div key={c.id} className={'kcol' + (over === c.id ? ' over' : '') + (c.id === POSTPONED ? ' dim' : '') + (c.items.length ? '' : ' empty')}
      onDragOver={e => { if (canDrag) { e.preventDefault(); if (over !== c.id) setOver(c.id) } }} onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOver('') }}
      onDrop={e => { e.preventDefault(); drop(c.id) }}>
      <div className="khead"><span>{c.name}</span><b>{c.items.length}</b></div>
      <div className="ksum">{c.sum ? mln(c.sum) : '—'}{WORK.includes(c.id) && c.debt ? <small>долг {mln(c.debt)}</small> : null}</div>
      {c.items.map(kcard)}
      {!c.items.length && <div className="kempty">{canDrag ? 'Перетащите сюда сделку' : 'Пусто'}</div>}
    </div>)}</div>
    {!shown.length && <p className="muted kbnone">{tone ? 'Таких сделок нет — снимите фильтр.' : s ? 'Ничего не найдено.' : 'На этой доске сделок нет.'}</p>}
    {canDrag && <p className="small muted kbhint">Карточку тяните мышью в другую стадию. Если для стадии чего-то не хватает, сделка останется на месте и покажет, что заполнить. На телефоне колонки листаются пальцем, стадия меняется в карточке сделки.</p>}
    {!canDrag && <p className="small muted kbhint">Дальше по работе сделку ведут кнопки в карточке: «В производство», «Работы сданы», «На закрытие».</p>}
  </>
}

// Воронка «Дизайн» — прежним списком по стадиям (её уберём, когда задачи на дизайн заменят воронку).
function FunnelList({ list, all, st, setSt, s, open }) {
  const groups = {}
  list.forEach(d => { (groups[d.stage] ||= { name: d.stage_name, sort: d.stage_sort, items: [], sum: 0, stale: 0 }); const g = groups[d.stage]; g.items.push(d); g.sum += d.sum || 0; if (ageDays(d.active || d.modified) >= IDLE) g.stale++ })
  const stages = Object.entries(groups).sort((a, b) => a[1].sort - b[1].sort)
  const cur = s ? 'all' : st && (st === 'all' || groups[st]) ? st : (stages.find(([, g]) => g.stale) || stages[0] || ['all'])[0]
  const shown = cur === 'all' ? stages : stages.filter(([id]) => id === cur)
  const row = d => { const age = ageDays(d.active || d.modified)
    return <div key={d.id} className="qrow deal" onClick={() => open(d.id)}>
      <span className="ic deal">№</span>
      <div className="qmain"><div className="qt"><b>№ {d.id}</b> {cleanTitle(d.title, d.id)}</div>
        <div className="small muted">{[d.city, d.area ? d.area + ' м²' : '', money(d.sum), all ? d.manager : ''].filter(Boolean).join(' · ')}</div></div>
      <span className={'badge' + (age >= IDLE ? ' hot' : '')}>{age ? `${age} дн.` : 'сегодня'}</span>
    </div> }
  return <>
    {stages.length > 0 && <div className="chips scroll">
      <button className={cur === 'all' ? 'on' : ''} onClick={() => setSt('all')}>Все <span>{list.length}</span></button>
      {stages.map(([id, g]) => <button key={id} className={cur === id ? 'on' : ''} onClick={() => setSt(id)}>{g.name} <span>{g.items.length}</span>{g.stale ? <i className="dot" /> : null}</button>)}
    </div>}
    <div className="card">
      {!list.length && <p className="muted">В этой воронке открытых сделок нет.</p>}
      {shown.map(([id, g]) => <div key={id} className="stage">
        {cur === 'all' ? <div className="stagehead"><span>{g.name}</span>
          <span className="small"><b>{g.items.length}</b> · {money(g.sum)}{g.stale ? <span className="badge hot">{g.stale} стоят</span> : null}</span></div>
          : <p className="small muted stagesum">{money(g.sum)}{g.stale ? <span className="badge hot">{g.stale} стоят</span> : null}</p>}
        {g.items.map(row)}
      </div>)}
    </div>
  </>
}

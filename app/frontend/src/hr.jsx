import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Copy } from './ui.jsx'
import './hr.css'
import { OnboardStatus } from './onboard.jsx'

// «Команда → Кандидаты» (HEAD 26.11 «отдел HR»): анкеты по ссылке-вакансии, шаги до «Принять», подсказка уровня по ответам.
// Видит только HEAD. Строка в «Базе кандидатов» и «Сотрудниках» пишется сервером сама (hr_sheets.py).
const STAGE = [['new', 'Новые'], ['talk', 'Связались'], ['interview', 'Собеседование'], ['trial', 'Пробная'],
  ['hired', 'Приняты'], ['reserve', 'Резерв'], ['rejected', 'Отказ']]
const STAGE1 = { new: 'Новый', talk: 'Связались', interview: 'Собеседование', trial: 'Пробная смена', hired: 'Принят', reserve: 'Резерв', rejected: 'Отказ' }
const SHORT = { art: 'Художники', print: 'Печать', mop: 'Продажи', design: 'Дизайн', video: 'Видео' }
const SRC = [['instagram', 'Instagram'], ['threads', 'Threads'], ['olx', 'OLX'], ['hh', 'hh.kz'], ['friend', 'от друзей']]
const days = iso => Math.floor((Date.now() - new Date(iso)) / 864e5)
const ago = iso => { const d = days(iso); return d < 1 ? 'сегодня' : d === 1 ? 'вчера' : `${d} дн.` }
const wa = (c, text) => `https://wa.me/7${c.phone.slice(1)}?text=${encodeURIComponent(text)}`
const hello = c => `Здравствуйте, ${c.full_name.split(' ').slice(-1)[0]}! Это ARTGAME, вы оставили анкету «${c.dir_title}». Удобно созвониться сегодня или завтра?`

export function TeamTabs({ children }) {
  const [v, setV] = useState(() => { try { return sessionStorage.getItem('artgame.team.v') || 'team' } catch { return 'team' } })
  const [n, setN] = useState(0)
  useEffect(() => { api('/hr/candidates').then(b => setN(b.new), () => {}) }, [])
  const pick = x => { setV(x); try { sessionStorage.setItem('artgame.team.v', x) } catch { /* */ } }
  return <>
    <div className="segf hrtabs"><button className={v === 'team' ? 'on' : ''} onClick={() => pick('team')}>Команда</button>
      <button className={v === 'hr' ? 'on' : ''} onClick={() => pick('hr')}>Кандидаты{n ? <b className="hrn">{n}</b> : null}</button></div>
    {v === 'hr' ? <Candidates onCount={setN} /> : children}
  </>
}

export function Candidates({ onCount }) {
  const [b, setB] = useState(null)
  const [dir, setDir] = useState('')
  const [stage, setStage] = useState('new')
  const [open, setOpen] = useState(null)
  const [links, setLinks] = useState(false)
  const load = () => api('/hr/candidates').then(x => { setB(x); onCount?.(x.new) }, () => setB({ items: [], dirs: {}, links: {} }))
  useEffect(() => { load() }, [])
  if (!b) return <div className="card muted">Загрузка…</div>
  if (open) return <CandCard id={open} back={() => { setOpen(null); load() }} />
  const list = b.items.filter(c => !dir || c.dir === dir)
  const by = k => list.filter(c => c.stage === k)
  const shown = by(stage)
  return <>
    <div className="card hrhead">
      <div className="hrrow"><h2>Кандидаты</h2><button className="ghost mini" onClick={() => setLinks(!links)}>{links ? 'Скрыть ссылки' : 'Ссылки-вакансии'}</button></div>
      <p className="muted small">Анкета по ссылке без входа. Новые — ответить за 2 дня{b.waiting ? <>, <b className="hrhot">ждут дольше: {b.waiting}</b></> : null}.</p>
      {links && <div className="hrlinks">{Object.entries(b.links).map(([d, path]) => <div key={d} className="hrlink">
        <b>{b.dirs[d]}</b><div className="hrsrc">{SRC.map(([s, t]) => { const url = `${location.origin}${path}&src=${s}`
          return <Copy key={s} text={url} label={t} /> })}</div></div>)}
        <p className="muted small">Ссылка с меткой показывает, откуда пришёл человек.</p></div>}
    </div>
    <div className="hrstages hrdirs">{[['', 'Все'], ...Object.entries(b.dirs).map(([k, t]) => [k, SHORT[k] || t])].map(([k, t]) => <button key={k} className={dir === k ? 'on' : ''} onClick={() => setDir(k)}>{t}</button>)}</div>
    <div className="hrstages">{STAGE.map(([k, t]) => { const n = by(k).length
      return <button key={k} className={stage === k ? 'on' : n ? '' : 'none'} onClick={() => setStage(k)}>{t}<b>{n}</b></button> })}</div>
    {!shown.length && <div className="card muted">{stage === 'new' ? 'Новых анкет нет. Скопируй ссылку-вакансию и поставь её в Instagram, OLX или hh.kz.' : 'Здесь пока никого.'}</div>}
    <div className="hrlist">{shown.map(c => <button key={c.id} className="hritem" onClick={() => setOpen(c.id)}>
      {c.thumb ? <img src={c.thumb} alt="" loading="lazy" /> : <span className="hrnoimg">{c.full_name[0]}</span>}
      <span className="hrmain"><b>{c.full_name}</b><span className="muted small">{c.dir_title} · {c.city || '—'} · {ago(c.created_at)}</span>
        <span className="hrtags">{c.level_title && <i className="tag okt">≈ {c.level_title}</i>}
          {c.stars ? <i className="tag">{'★'.repeat(c.stars)}</i> : null}
          {c.prior?.status && <i className="tag hrwarn">уже был: {c.prior.status}</i>}
          {c.waiting && <i className="tag hott">ждёт {days(c.stage_at)} дн.</i>}
          {!c.submitted && <i className="tag">не дописал</i>}
          {c.trial_on && c.stage === 'trial' && <i className="tag">пробная {c.trial_on.slice(8, 10)}.{c.trial_on.slice(5, 7)}</i>}</span></span>
    </button>)}</div>
  </>
}

function Answers({ c }) {
  const a = c.answers || {}
  const val = it => { const v = a[it.key], o = a[it.key + '_other']
    const s = Array.isArray(v) ? v.join(', ') : v || ''
    return [s, o].filter(Boolean).join(' · ') }
  return (c.steps || []).slice(1).map((s, n) => { const rows = s.items.filter(it => it.t !== 'resume' && val(it))
    return rows.length ? <div key={n} className="card hrans"><h3>{s.title[0]}</h3>
      {rows.map(it => <div key={it.key} className="hrqa"><span>{it.q[0]}</span><b>{val(it)}</b></div>)}</div> : null })
}

function CandCard({ id, back }) {
  const [c, setC] = useState(null)
  const [err, setErr] = useState('')
  const [act, setAct] = useState('')   // какое действие раскрыто: interview / trial / hired / reserve / rejected
  const [f, setF] = useState({})
  const load = () => api(`/hr/candidates/${id}`).then(x => { setC(x); setF({ note: x.note || '', hired_role: x.hired_role || x.roles?.[0]?.[0] || '' }) }, e => setErr(e.message))
  useEffect(() => { load() }, [id])
  if (!c) return <div className="card muted">{err || 'Загрузка…'}</div>
  const save = body => api(`/hr/candidates/${id}`, { method: 'POST', body }).then(() => { setAct(''); setErr(''); load() }, e => setErr(e.message))
  const photos = c.files.filter(x => x.kind === 'photo'), resume = c.files.filter(x => x.kind === 'resume')
  const h = c.hint
  const roleTitle = Object.fromEntries(c.roles || [])
  return <>
    <button className="ghost mini hrback" onClick={back}>← Кандидаты</button>
    <div className="card">
      <div className="hrrow"><div><h2>{c.full_name}</h2><p className="muted small">{c.dir_title} · {c.city} · {c.source ? `пришёл: ${c.source} · ` : ''}{ago(c.created_at)}</p></div>
        <i className={'tag ' + (c.stage === 'hired' ? 'okt' : c.stage === 'rejected' ? 'hott' : '')}>{STAGE1[c.stage]}</i></div>
      {c.waiting && <p className="hrhot small">Ждёт ответа {days(c.stage_at)} дн. — мы обещали за 2 дня.</p>}
      {c.prior?.status && <p className="small hrprior">Уже был в базе: лист «{c.prior.sheet}», статус «{c.prior.status}»{c.prior.contact ? `, ${c.prior.contact}` : ''}{c.prior.comment ? ` — ${c.prior.comment}` : ''}</p>}
      <div className="hrrow hrcontact"><b>{c.phone.replace(/(\d)(\d{3})(\d{3})(\d{2})(\d{2})/, '$1 $2 $3 $4 $5')}</b>
        <a className="btn ghost mini" href={wa(c, hello(c))} target="_blank" rel="noreferrer">WhatsApp</a><Copy text={c.phone} label="Номер" /></div>
    </div>
    {h && <div className="card hrhint"><div className="hrrow"><h3>Уровень по ответам</h3><b className="ok">≈ {h.title} · {h.score} из {h.max}</b></div>
      <p className="small muted">{h.why.length ? h.why.join(' · ') : 'опыта в ответах нет'}</p>
      <p className="small muted">Старт у всех — с первой ступени. Подсказка — с кем можно идти на экзамен быстрее.</p></div>}
    {photos.length > 0 && <div className="hrpics">{photos.map(p => <a key={p.id} href={p.url} target="_blank" rel="noreferrer">{p.thumb ? <img src={p.thumb} alt="" loading="lazy" /> : <span>фото</span>}</a>)}</div>}
    {(resume.length > 0 || c.answers?.resume_text || c.answers?.portfolio) && <div className="card"><h3>Резюме и портфолио</h3>
      {resume.map(r => <p key={r.id}><a href={r.url} target="_blank" rel="noreferrer">📄 {r.name}</a></p>)}
      {c.answers?.portfolio && <p className="small">{c.answers.portfolio}</p>}
      {c.answers?.resume_text && <p className="small hrpre">{c.answers.resume_text}</p>}
      {c.folder && <p className="small"><a href={c.folder} target="_blank" rel="noreferrer">Папка кандидата на Диске</a></p>}</div>}
    <Answers c={c} />
    <div className="card">
      <h3>Оценка и заметка</h3>
      <div className="hrstars">{[1, 2, 3, 4, 5].map(n => <button key={n} className={n <= (c.stars || 0) ? 'on' : ''} aria-label={`${n} из 5`} onClick={() => save({ stars: n === c.stars ? 0 : n })}>★</button>)}</div>
      <textarea rows={3} value={f.note} placeholder="Что увидел на разговоре: сильные стороны, сомнения" onChange={e => setF({ ...f, note: e.target.value })} />
      {f.note !== (c.note || '') && <button className="ghost" onClick={() => save({ note: f.note })}>Сохранить заметку</button>}
    </div>
    <div className="card hracts">
      <h3>Следующий шаг</h3>
      <div className="hrbtns">
        {c.stage === 'new' && <button className="ghost" onClick={() => save({ stage: 'talk' })}>Связались</button>}
        {['new', 'talk'].includes(c.stage) && <button className="ghost" onClick={() => setAct(act === 'interview' ? '' : 'interview')}>Собеседование</button>}
        {['new', 'talk', 'interview'].includes(c.stage) && <button className="ghost" onClick={() => setAct(act === 'trial' ? '' : 'trial')}>Пробная смена</button>}
        {c.stage !== 'hired' && <button onClick={() => setAct(act === 'hired' ? '' : 'hired')}>Принять в команду</button>}
        {!['reserve', 'hired'].includes(c.stage) && <button className="ghost" onClick={() => setAct(act === 'reserve' ? '' : 'reserve')}>В резерв</button>}
        {!['rejected', 'hired'].includes(c.stage) && <button className="ghost" onClick={() => setAct(act === 'rejected' ? '' : 'rejected')}>Отказ</button>}
        {['reserve', 'rejected'].includes(c.stage) && <button className="ghost" onClick={() => save({ stage: 'talk' })}>Вернуть в работу</button>}
      </div>
      {act === 'interview' && <div className="hrform"><label>Когда собеседование</label><input type="date" value={f.meet_on || ''} onChange={e => setF({ ...f, meet_on: e.target.value })} />
        <button disabled={!f.meet_on} onClick={() => save({ stage: 'interview', meet_on: f.meet_on })}>Назначить</button></div>}
      {act === 'trial' && <div className="hrform"><p className="small muted">Пробная оплачивается, только если человека примем: начисление в ФОТ появится само, когда он войдёт в приложение. Не приняли — не оплачивается.</p><label>Дата пробной смены</label><input type="date" value={f.trial_on || ''} onChange={e => setF({ ...f, trial_on: e.target.value })} />
        <label>Сделка (необязательно)</label><input inputMode="numeric" value={f.trial_object || ''} placeholder="№ сделки" onChange={e => setF({ ...f, trial_object: e.target.value.replace(/\D/g, '') })} />
        <button disabled={!f.trial_on} onClick={() => save({ stage: 'trial', trial_on: f.trial_on, ...(f.trial_object ? { trial_object: +f.trial_object } : {}) })}>Назначить пробную</button></div>}
      {act === 'hired' && <div className="hrform"><label>С какой роли начинает</label>
        <div className="segf">{(c.roles || []).map(([k, t]) => <button key={k} className={f.hired_role === k ? 'on' : ''} onClick={() => setF({ ...f, hired_role: k })}>{t}</button>)}</div>
        <p className="small muted">Все начинают с первой ступени. Человек входит в бот ARTGAME → «ARTGAME», вводит имя и этот же телефон — роль «{roleTitle[f.hired_role]}» встанет сама. Строка уйдёт в «Сотрудники и суппорты». До первой смены он прочитает правила роли, ТБ и примет соглашение о неразглашении.</p>
        <button disabled={!f.hired_role} onClick={() => save({ stage: 'hired', hired_role: f.hired_role })}>Принять</button></div>}
      {(act === 'reserve' || act === 'rejected') && <div className="hrform"><label>Почему</label>
        <input value={f.reason || ''} maxLength={200} placeholder={act === 'reserve' ? 'нет набора в городе, позвать весной…' : 'слабые работы, не пришёл, не профиль…'} onChange={e => setF({ ...f, reason: e.target.value })} />
        {act === 'rejected' && <label className="hrcheck"><input type="checkbox" checked={!!f.self_refused} onChange={e => setF({ ...f, self_refused: e.target.checked })} /> Отказался сам (в базе — «Не актуален»)</label>}
        <button disabled={!(f.reason || '').trim()} onClick={() => save({ stage: act, reason: f.reason, ...(act === 'rejected' ? { self_refused: !!f.self_refused } : {}) })}>{act === 'reserve' ? 'В резерв' : 'Отказать'}</button></div>}
      {c.stage === 'hired' && c.trial_on && <p className="small muted">{c.trial_paid ? `✓ Пробная смена ${c.trial_on.slice(8, 10)}.${c.trial_on.slice(5, 7)} начислена в ФОТ.` : `Пробная смена ${c.trial_on.slice(8, 10)}.${c.trial_on.slice(5, 7)} начислится в ФОТ, когда войдёт в приложение.`}</p>}
      {c.stage === 'hired' && <p className="small muted">{c.person_id ? '✓ Вошёл в приложение, роль стоит.' : `Ждём, когда войдёт в приложение с телефоном ${c.phone}. Можно отправить ему ссылку на бот.`}</p>}
      {c.stage === 'hired' && c.person_id && <OnboardStatus ob={c.onboard} />}
      {c.stage === 'hired' && !c.person_id && <a className="btn ghost mini" href={wa(c, `Вы в команде ARTGAME! Откройте бот ARTGAME в Telegram, нажмите «Старт», потом «ARTGAME» внизу и введите имя и этот номер — ${c.phone}.`)} target="_blank" rel="noreferrer">Написать в WhatsApp, как войти</a>}
      {err && <p className="hrerr">{err}</p>}
    </div>
    <p className="small muted hrsheet">{c.in_sheet ? '✓ Строка в «Базе кандидатов» обновлена.' : 'Строка в «Базе кандидатов» появится после отправки анкеты.'}</p>
  </>
}

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
const day2 = d => d ? `${d.slice(8, 10)}.${d.slice(5, 7)}` : ''
const meLink = c => `${location.origin}/?me=${c.token}`
// Приглашение на пробный день (HEAD 28.11): тот же текст, что на личной странице кандидата, плюс ссылка на неё
const trialText = (c, v) => v.state !== 'ok' ?
  `Здравствуйте, ${c.full_name.split(' ').slice(-1)[0]}! Это ARTGAME. Приглашаем вас на пробный день — день работы на объекте с куратором. Выберите удобный день по ссылке, куратор подтвердит и пришлёт время и адрес: ${meLink(c)}` :
  [`Здравствуйте, ${c.full_name.split(' ').slice(-1)[0]}! Это ARTGAME. Ждём вас на пробный день.`,
  `Когда: ${day2(v.day)}${v.time ? `, в ${v.time}` : ''}`, v.place && `Куда: ${v.place}`,
  v.who && `Встретит: ${v.who}${v.who_phone ? `, ${v.who_phone}` : ''}`, v.bring && `Взять с собой: ${v.bring}`,
  'Пробный день оплачивается, если вас возьмут в команду. Если не получается прийти — сразу сообщите куратору.',
  `Подробнее: ${meLink(c)}`].filter(Boolean).join('\n')
const STATE = { pick: 'Кандидат выбирает день', wait: 'Ждёт подтверждения куратора ГИП', ok: 'День подтверждён' }
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
        <a className="btn ghost mini" href={wa(c, hello(c))} target="_blank" rel="noreferrer">WhatsApp</a><Copy text={c.phone} label="Номер" />
        {/* HEAD 28.11 «только Telegram»: кто оставил анкету до кнопки бота — одна ссылка, дальше бот пишет сам */}
        {c.bot ? <span className="small ok">✓ в Telegram</span> : <Copy text={`https://t.me/artgame_team_bot?start=c_${c.token}`} label="Ссылка на бот" />}</div>
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
    <TrialBlock c={c} save={save} />
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
      {act === 'trial' && <div className="hrform"><p className="small muted">Пробная оплачивается, только если человека примем: начисление в ФОТ появится само, когда он войдёт в приложение. Не приняли — не оплачивается.</p><label>Дата пробной смены — пусто: кандидат выберет сам, куратор подтвердит</label><input type="date" value={f.trial_on || ''} onChange={e => setF({ ...f, trial_on: e.target.value })} />
        <label>Проект — его куратор ГИП оценит пробный день</label><select value={f.trial_object || ''} onChange={e => setF({ ...f, trial_object: e.target.value })}>
          <option value="">Выбрать проект в работе…</option>{(c.objects || []).map(o => <option key={o.id} value={o.id}>№{o.id} {o.title}{o.city ? ` · ${o.city}` : ''} · {o.gip ? `ГИП ${o.gip}` : 'без ГИП'}</option>)}</select>
        <label>Кто оценивает и встречает</label><select value={f.trial_by || ''} onChange={e => setF({ ...f, trial_by: e.target.value })}>
          <option value="">Куратор ГИП сделки</option>{(c.evaluators || []).map(([pid, n]) => <option key={pid} value={pid}>{n}</option>)}</select>
        <p className="small muted">Время, адрес и «что взять» указывает куратор ГИП, когда подтверждает день. Кандидат в Telegram получит всё от бота сам, без Telegram — кнопка WhatsApp в карточке.</p>
        <button onClick={() => save({ stage: 'trial', ...(f.trial_on ? { trial_on: f.trial_on } : {}),
          ...(f.trial_object ? { trial_object: +f.trial_object } : {}), ...(f.trial_by ? { trial_by: +f.trial_by } : {}) })}>Назначить пробную</button></div>}
      {act === 'hired' && <div className="hrform"><label>С какой роли начинает</label>
        <div className="segf">{(c.roles || []).map(([k, t]) => <button key={k} className={f.hired_role === k ? 'on' : ''} onClick={() => setF({ ...f, hired_role: k })}>{t}</button>)}</div>
        <p className="small muted">Все начинают с первой ступени. Человек входит в бот ARTGAME → «ARTGAME», вводит имя и этот же телефон — роль «{roleTitle[f.hired_role]}» встанет сама. Строка уйдёт в «Сотрудники и суппорты». До первой смены он прочитает правила роли, ТБ и примет соглашение о неразглашении.</p>
        <button disabled={!f.hired_role} onClick={() => save({ stage: 'hired', hired_role: f.hired_role })}>Принять</button></div>}
      {(act === 'reserve' || act === 'rejected') && <div className="hrform"><label>Почему</label>
        <input value={f.reason || ''} maxLength={200} placeholder={act === 'reserve' ? 'нет набора в городе, позвать весной…' : 'слабые работы, не пришёл, не профиль…'} onChange={e => setF({ ...f, reason: e.target.value })} />
        {act === 'rejected' && <label className="hrcheck"><input type="checkbox" checked={!!f.self_refused} onChange={e => setF({ ...f, self_refused: e.target.checked })} /> Отказался сам (в базе — «Не актуален»)</label>}
        <button disabled={!(f.reason || '').trim()} onClick={() => save({ stage: act, reason: f.reason, ...(act === 'rejected' ? { self_refused: !!f.self_refused } : {}) })}>{act === 'reserve' ? 'В резерв' : 'Отказать'}</button></div>}
      {c.stage === 'interview' && c.meet_on && <a className="btn ghost mini" href={wa(c, `Здравствуйте, ${c.full_name.split(' ').slice(-1)[0]}! Это ARTGAME. Приглашаем на собеседование ${day2(c.meet_on)}. Во сколько вам удобно?`)} target="_blank" rel="noreferrer">Пригласить на собеседование в WhatsApp</a>}
      {['reserve', 'rejected'].includes(c.stage) && <a className="btn ghost mini" href={wa(c, `Здравствуйте, ${c.full_name.split(' ').slice(-1)[0]}! Это ARTGAME. Спасибо за анкету и потраченное время. Сейчас позвать в команду не можем, но анкета осталась у нас: когда появится место, напишем.`)} target="_blank" rel="noreferrer">Вежливо ответить в WhatsApp</a>}
      {c.stage === 'hired' && c.trial_on && <p className="small muted">{c.trial_paid ? `✓ Пробная смена ${c.trial_on.slice(8, 10)}.${c.trial_on.slice(5, 7)} начислена в ФОТ.` : `Пробная смена ${c.trial_on.slice(8, 10)}.${c.trial_on.slice(5, 7)} начислится в ФОТ, когда войдёт в приложение.`}</p>}
      {c.stage === 'hired' && <p className="small muted">{c.person_id ? '✓ Вошёл в приложение, роль стоит.' : `Ждём, когда войдёт в приложение с телефоном ${c.phone}. Можно отправить ему ссылку на бот.`}</p>}
      {c.stage === 'hired' && c.person_id && <OnboardStatus ob={c.onboard} />}
      {c.stage === 'hired' && !c.person_id && <a className="btn ghost mini" href={wa(c, `Вы в команде ARTGAME! Откройте бот ARTGAME в Telegram, нажмите «Старт», потом «ARTGAME» внизу и введите имя и этот номер — ${c.phone}.`)} target="_blank" rel="noreferrer">Написать в WhatsApp, как войти</a>}
      {err && <p className="hrerr">{err}</p>}
      {/* HEAD 28.11 «просто удали»: тестовая или ошибочная анкета — насовсем, с подтверждением */}
      {!c.person_id && (act === 'delete' ? <div className="hrform hrdel"><p className="small">Удалить анкету {c.full_name} насовсем? Пропадёт из «Кандидатов», строка — из «Базы кандидатов», папка с фото — в корзину Диска.</p>
        <div className="hrrow"><button className="ghost" onClick={() => setAct('')}>Отмена</button>
          <button className="hot" onClick={() => api(`/hr/candidates/${id}`, { method: 'DELETE' }).then(back, e => setErr(e.message))}>Удалить</button></div></div> :
        <button className="ghost mini hrdelbtn" onClick={() => setAct('delete')}>Удалить анкету</button>)}
    </div>
    <p className="small muted hrsheet">{c.in_sheet ? '✓ Строка в «Базе кандидатов» обновлена.' : 'Строка в «Базе кандидатов» появится после отправки анкеты.'}</p>
  </>
}


// Пробный день (HEAD 28.11): кто оценивает и оценка куратора целиком — звёзды, пункты, итог, комментарий.
function TrialBlock({ c, save }) {
  const t = c.trial
  const [sent, setSent] = useState(null)
  if (!t) return null
  const day = day2(c.trial_on)
  const v = t.invite || {}, sentAt = sent || v.sent_at
  const mark = () => api(`/hr/candidates/${c.id}/invite-sent`, { method: 'POST' }).then(r => setSent(r.sent_at), () => {})
  if (!t.at) return <div className={'card hrtrial' + (t.late ? ' late' : '')}><h3>Пробный день {day || '— день выбирает кандидат'}{c.trial_time ? `, ${c.trial_time}` : ''}</h3>
    {t.by ? <p className="small">Оценивает и встречает: <b>{t.by_name}</b>{t.by === t.gip ? ' · куратор ГИП сделки' : ''}. {t.late ? 'День прошёл, оценки ещё нет.' : 'Оценка появится здесь после смены.'}</p> :
      <p className="small hrerr">Оценщик не назначен: у сделки нет куратора ГИП. Выбери, кто оценит.</p>}
    {t.by && !t.by_bot && <p className="small hrerr">{t.by_name} не вошёл в бот: уведомление ему не придёт. Позвони и скажи, что карточка — вверху приложения.</p>}
    {c.stage === 'trial' && <div className="hrinvite">
      <p className="small"><b>{STATE[v.state]}</b>{v.state === 'ok' && v.place ? ` · ${v.place}` : ''}</p>
      <p className={'small ' + (t.cand_bot ? 'ok' : 'muted')}>{t.cand_bot ? '✓ Кандидат в Telegram: бот сам пишет ему на каждом шаге и напоминает накануне.' :
        'Кандидат не подключил Telegram — отправь ему это сообщение в WhatsApp. Там же ссылка, где он выбирает день и может подключить бот.'}</p>
      {(!t.cand_bot || (v.state === 'ok' && !sentAt)) && <><p className="small hrpre">{trialText(c, v)}</p>
        <a className={'btn mini' + (sentAt ? ' ghost' : '')} href={wa(c, trialText(c, v))} target="_blank" rel="noreferrer" onClick={mark}>{sentAt ? 'Отправить ещё раз в WhatsApp' : 'Отправить кандидату в WhatsApp'}</a>
        {v.state === 'ok' && <p className={'small ' + (sentAt ? 'ok' : 'hrerr')}>{sentAt ? `✓ Приглашение отправлено ${new Date(sentAt).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}` : 'Кандидат ещё не знает время и адрес'}</p>}</>}
      {t.cand_bot && v.state === 'ok' && <p className={'small ' + (sentAt ? 'ok' : 'hrerr')}>{sentAt ? '✓ Приглашение ушло в Telegram' : 'Приглашение в Telegram не ушло — отправь в WhatsApp'}</p>}</div>}
    {c.stage === 'trial' && <select value={t.by || ''} onChange={e => e.target.value && save({ trial_by: +e.target.value })}>
      <option value="">{t.by ? 'Сменить оценщика…' : 'Выбрать оценщика…'}</option>{(c.evaluators || []).map(([pid, n]) => <option key={pid} value={pid}>{n}</option>)}</select>}
  </div>
  if (t.noshow) return <div className="card hrtrial no"><h3>Пробный день {day}</h3><p><b>Не пришёл.</b></p>
    <p className="small muted">Отметил {t.reviewer} · {new Date(t.at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</p></div>
  return <div className={'card hrtrial ' + t.verdict_code}><h3>Пробный день {day} · оценка</h3>
    <div className="hrtv"><span className="hrtstars">{'★'.repeat(t.stars)}<i>{'★'.repeat(5 - t.stars)}</i></span><b>{t.verdict}</b></div>
    <p className="small muted">{t.reviewer} · {new Date(t.at).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</p>
    <div className="hrtitems">{t.items.map(([k, v]) => <div key={k}><span>{k}</span><em className={v === 'Да' ? 'ok' : v === 'Нет' ? 'no' : ''}>{v}</em></div>)}</div>
    <p className="hrpre">{t.comment}</p></div>
}

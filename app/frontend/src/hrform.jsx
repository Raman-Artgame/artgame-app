import React, { useEffect, useState } from 'react'
import { shrink } from './work.jsx'
import './hrform.css'

// Анкета кандидата по ссылке (HEAD 26.11 «отдел HR»): /?job=art (&src=instagram) открывается без входа.
// Вопросы приходят с сервера (hr_forms.py) — экран их только рисует. Шагами, как бриф клиента, тёмная, как приложение.
// После шага «О себе» анкета уже сохранена (сервер даёт токен), дальше каждое «Дальше» её дописывает, фото и резюме
// уходят сразу на Диск. Ставок здесь нет (HEAD 26.11): шаг «Как у нас устроено» — старт с первой ступени и рост через экзамены.
// Ступень кандидат не выбирает — приложение подсказывает HEAD уровень по ответам.
// Черновик и токен — в памяти телефона: закрыл и открыл — продолжаешь с того же места.
const T = {
  next: ['Дальше', 'Әрі қарай'], back: ['Назад', 'Артқа'], send: ['Отправить анкету', 'Сауалнаманы жіберу'], of: ['из', '/'],
  time: ['5–7 минут', '5–7 минут'], hello: ['ARTGAME · набор в команду', 'ARTGAME · командаға қабылдау'],
  other: ['Свой вариант', 'Өз нұсқаң'], upTo: ['до', 'дейін'], photos: ['Фото работ (до 10)', 'Жұмыс суреттері (10-ға дейін)'], del: ['Убрать фото', 'Суретті алып тастау'],
  add: ['Добавить фото', 'Сурет қосу'], file: ['Файл PDF или Word', 'PDF немесе Word файлы'], write: ['Написать', 'Жазу'],
  resumeOk: ['Резюме загружено', 'Түйіндеме жүктелді'], need: ['Заполни поля со звёздочкой', 'Жұлдызшасы бар өрістерді толтыр'],
  fail: ['Не отправилось. Проверь интернет и нажми ещё раз.', 'Жіберілмеді. Интернетті тексеріп, қайта бас.'],
  sending: ['Отправляю…', 'Жіберілуде…'], bad: ['Такой вакансии нет. Попроси новую ссылку.', 'Мұндай вакансия жоқ. Жаңа сілтеме сұра.'],
  done: ['Спасибо! Анкета у нас', 'Рақмет! Сауалнама бізде'],
  doneText: ['Посмотрим работы и ответим в течение двух дней — в WhatsApp или Telegram.', 'Жұмыстарыңды қарап, екі күн ішінде WhatsApp немесе Telegram арқылы жауап береміз.'],
  again: ['Изменить ответы', 'Жауаптарды өзгерту'],
  skip: ['Не знаешь — пропусти, это нормально.', 'Білмесең — өткізіп жібер, бұл қалыпты.'],
}
const mem = (k, v) => { try { if (v === undefined) return JSON.parse(localStorage.getItem(k) || 'null'); localStorage.setItem(k, JSON.stringify(v)) } catch { return null } }
const post = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
const readFile = f => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = no; r.readAsDataURL(f) })

export function JobPage({ dir, src }) {
  const KEY = `artgame.job.${dir}`
  const saved = mem(KEY) || {}
  const [kk, setKk] = useState(saved.lang === 'kk')
  const [form, setForm] = useState(undefined)
  const [a, setA] = useState(saved.a || {})
  const [i, setI] = useState(saved.i || 0)
  const [token, setToken] = useState(saved.token || '')
  const [pics, setPics] = useState([])
  const [resume, setResume] = useState(saved.resume || '')   // '' | 'up' | 'ok' | 'bad'
  const [state, setState] = useState(saved.done ? 'done' : '')
  const [err, setErr] = useState('')
  const L = x => (x ? x[kk ? 1 : 0] : '')
  useEffect(() => { document.body.classList.add('hjpage'); document.title = 'ARTGAME — анкета кандидата'
    fetch(`/api/hr/form/${encodeURIComponent(dir)}`).then(r => r.ok ? r.json() : Promise.reject()).then(setForm, () => setForm(null)) }, [])
  useEffect(() => { mem(KEY, { a, i, token, resume, lang: kk ? 'kk' : 'ru', done: state === 'done' }) }, [a, i, token, resume, kk, state])
  // вернулся на страницу — свои фото с сервера, чтобы видеть и убирать
  useEffect(() => { if (token) fetch(`/api/hr/c/${token}`).then(r => r.ok ? r.json() : null).then(j => j?.photos?.length &&
    setPics(p => p.length ? p : j.photos.map(x => ({ id: 's' + x.id, fid: x.id, url: x.thumb, state: 'ok' })))).catch(() => {}) }, [token])
  const Top = <div className="hjtop"><b className="hjlogo">ARTGAME</b><div className="hjlang">
    <button className={!kk ? 'on' : ''} onClick={() => setKk(false)}>RU</button><button className={kk ? 'on' : ''} onClick={() => setKk(true)}>ҚАЗ</button></div></div>
  if (form === undefined) return <div className="hj"><p className="hjmuted">…</p></div>
  if (form === null) return <div className="hj">{Top}<div className="hjcard"><h2>{L(T.bad)}</h2></div></div>
  if (state === 'done') return <div className="hj">{Top}<div className="hjcard hjdone"><div className="hjok">✓</div><h1>{L(T.done)}</h1><p>{L(T.doneText)}</p>
    <button className="hjghost" onClick={() => { setState(''); setI(0) }}>{L(T.again)}</button></div>
    {token && <CandStatus token={token} inline />}</div>

  const steps = form.steps, s = steps[i], last = i === steps.length - 1
  const set = (k, v) => setA(x => ({ ...x, [k]: v }))
  const missing = s.items.filter(it => it.req && !(a[it.key] || '').trim())
  const save = async () => {
    const r = await post('/api/hr/apply', { dir, answers: a, lang: kk ? 'kk' : 'ru', src })
    const j = await r.json().catch(() => ({}))
    if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : L(T.fail))
    setToken(j.token); return j.token
  }
  const go = async () => {
    setErr('')
    if (missing.length) return setErr(L(T.need))
    try {
      if (i === 0 || last) { setState('sending'); await save() } else if (token) save().catch(() => {})   // дописываем молча
      if (last) { const t = token || await save(); const r = await post(`/api/hr/c/${t}/done`, {}); if (!r.ok) throw new Error(L(T.fail)); setState('done') }
      else { setState(''); setI(i + 1); window.scrollTo(0, 0) }
    } catch (e) { setState(''); setErr(e.message || L(T.fail)) }
  }
  // HEAD 27.11 «очень долго»: фото грузим по 3 сразу (было строго по одному), у каждого — ✕ «убрать»
  const addPics = async list => {
    const add = [...list].slice(0, 10 - pics.length).map(f => ({ f, id: Math.random().toString(36).slice(2), url: URL.createObjectURL(f), state: 'up' }))
    setPics(p => [...p, ...add.map(({ f, ...x }) => x)])
    const one = async ({ f, id }) => {
      try { const data = await shrink(f); const r = await post(`/api/hr/c/${token}/file`, { kind: 'photo', data }); const j = await r.json().catch(() => ({}))
        setPics(p => p.map(x => x.id === id ? { ...x, state: r.ok ? 'ok' : 'bad', fid: j.id, why: !r.ok && typeof j.detail === 'string' ? j.detail : '' } : x))
      } catch { setPics(p => p.map(x => x.id === id ? { ...x, state: 'bad' } : x)) }
    }
    const queue = [...add]
    await Promise.all([0, 1, 2].map(async () => { while (queue.length) await one(queue.shift()) }))
  }
  const dropPic = async p => {
    setPics(x => x.filter(y => y.id !== p.id))
    if (p.fid) fetch(`/api/hr/c/${token}/file/${p.fid}`, { method: 'DELETE' }).catch(() => {})
  }
  const addResume = async f => { setResume('up')
    try { const data = await readFile(f); const r = await post(`/api/hr/c/${token}/file`, { kind: 'resume', data }); setResume(r.ok ? 'ok' : 'bad') } catch { setResume('bad') } }

  const Chips = it => { const cur = Array.isArray(a[it.key]) ? a[it.key] : (it.t === 'one' && a[it.key] ? [a[it.key]] : [])
    const tap = v => it.t === 'one' ? set(it.key, cur.includes(v) ? '' : v)
      : set(it.key, cur.includes(v) ? cur.filter(x => x !== v) : it.max && cur.length >= it.max ? [...cur.slice(1), v] : [...cur, v])
    return <div className="hjchips">{it.opts.map(o => <button key={o[0]} className={cur.includes(o[0]) ? 'on' : ''} onClick={() => tap(o[0])}>{kk ? o[1] : o[0]}</button>)}</div> }
  const Item = it => {
    if (it.t === 'chips' || it.t === 'one') return <div key={it.key} className="hjq"><h3>{L(it.q)}</h3>{it.hint && <p className="hjmuted">{L(it.hint)}</p>}{Chips(it)}
      {it.other && <input className="hjin" value={a[it.key + '_other'] || ''} maxLength={120} placeholder={L(T.other)} onChange={e => set(it.key + '_other', e.target.value)} />}</div>
    if (it.t === 'resume') return <div key={it.key} className="hjq"><h3>{L(it.q)}</h3>
      <div className="hjrow"><label className={'hjfile ' + resume}>{resume === 'ok' ? '✓ ' + L(T.resumeOk) : resume === 'up' ? L(T.sending) : L(T.file)}
        <input type="file" accept=".pdf,.doc,.docx,image/*" hidden onChange={e => { const f = e.target.files[0]; f && addResume(f); e.target.value = '' }} /></label></div>
      <textarea className="hjin" rows={4} value={a.resume_text || ''} maxLength={4000} placeholder={L(T.write)} onChange={e => set('resume_text', e.target.value)} /></div>
    const Tag = it.long ? 'textarea' : 'input'
    return <label key={it.key} className="hjq hjfield"><h3>{L(it.q)}{it.req ? ' *' : ''}</h3>
      <Tag className="hjin" rows={it.long ? 3 : undefined} value={a[it.key] || ''} maxLength={it.long ? 1200 : 200} placeholder={L(it.ph)}
        inputMode={it.kind === 'tel' ? 'tel' : it.kind === 'date' ? 'numeric' : 'text'} onChange={e => set(it.key, e.target.value)} /></label>
  }
  return <div className="hj">{Top}
    <p className="hjmuted">{L(T.hello)}</p><h1>{L(form.title)}</h1>
    {i === 0 && <p className="hjlead">{L(form.lead)}</p>}
    <p className="hjmuted">{i + 1} {L(T.of)} {steps.length} · {L(T.time)}</p>
    <div className="hjbar">{steps.map((_, k) => <i key={k} className={k <= i ? 'on' : ''} />)}</div>
    <div className="hjcard"><h2>{L(s.title)}</h2>
      {s.intro && <div className="hjintro">{s.intro.map(([k, v], n) => <div key={n} className="hjiv"><span>{L(k)}</span><b>{L(v)}</b></div>)}</div>}
      {s.photos && <div className="hjq"><h3>{L(T.photos)}</h3><div className="hjpics">{pics.map(p => <span key={p.id} className={'hjpic ' + p.state} title={p.why || ''}><img src={p.url} alt="" />
        {p.state !== 'up' && <button type="button" className="hjdel" aria-label={L(T.del)} onClick={() => dropPic(p)}>✕</button>}</span>)}
        {pics.length < 10 && <label className="hjpic add"><span>＋</span><em>{L(T.add)}</em>
          <input type="file" accept="image/*" multiple hidden onChange={e => { const f = e.target.files; f.length && addPics(f); e.target.value = '' }} /></label>}</div></div>}
      {s.items.map(Item)}
      {i > 0 && <p className="hjmuted hjskip">{L(T.skip)}</p>}
    </div>
    {err && <p className="hjfail">{err}</p>}
    <div className="hjnav">{i > 0 && <button className="hjghost" onClick={() => { setErr(''); setI(i - 1); window.scrollTo(0, 0) }}>{L(T.back)}</button>}
      <button className="hjgo" disabled={state === 'sending' || pics.some(p => p.state === 'up') || resume === 'up'} onClick={go}>
        {state === 'sending' ? L(T.sending) : last ? L(T.send) : L(T.next)}</button></div>
  </div>
}


// Личная страница кандидата (HEAD 28.11 «как кандидат получит информацию?»): /?me=ТОКЕН, без входа.
// Ссылка уходит в WhatsApp вместе с приглашением; та же карточка — под «Спасибо» в анкете. Оценок и причин здесь нет.
const BOT = 'artgame_team_bot'
const tgLink = token => `https://t.me/${BOT}?start=c_${token}`
const fmtDay = d => d ? new Date(d + 'T00:00:00').toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' }) : ''
export function CandStatus({ token, inline }) {
  const [j, setJ] = useState(undefined)
  const [busy, setBusy] = useState(''), [err, setErr] = useState('')
  const load = () => fetch(`/api/hr/c/${token}`).then(r => r.ok ? r.json() : null).then(setJ, () => setJ(null))
  useEffect(() => { load() }, [token])
  const s = j?.status
  const pick = async d => {
    setBusy(d); setErr('')
    try { const r = await post(`/api/hr/c/${token}/trial-day`, { day: d }); if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'Не получилось'); await load() }
    catch (e) { setErr(e.message) }
    setBusy('')
  }
  // кнопка бота: без неё бот не может написать первым (правило Telegram)
  const tg = j && !j.bot && <a className="hjtg" href={tgLink(token)} target="_blank" rel="noreferrer">Получать ответы в Telegram</a>
  if (inline && (!s || s.step === 'got')) return j && !j.bot ? <div className="hjcard hjme"><p className="hjmuted">Ответ по анкете, приглашение и напоминания пришлёт бот ARTGAME — нажми и «Старт».</p>{tg}</div> : null
  const box = body => inline ? <div className="hjcard hjme">{body}</div> :
    <div className="hj"><div className="hjtop"><b className="hjlogo">ARTGAME</b></div><div className="hjcard hjme">{body}</div></div>
  if (j === undefined) return inline ? null : <div className="hj"><p className="hjmuted">…</p></div>
  if (!s) return box(<h2>Ссылка не работает. Напиши нам в WhatsApp.</h2>)
  const hi = j.name ? `${j.name}, ` : ''
  if (s.step === 'trial' && s.state !== 'ok') return box(<>
    <span className="hjtag">Пробный день</span>
    <h1>{hi}{s.state === 'wait' ? 'день выбран' : 'выбери день для пробной смены'}</h1>
    {s.state === 'wait' && <p>{fmtDay(s.day)} — ждём подтверждения куратора. Время и адрес придут {j.bot ? 'в Telegram' : 'в WhatsApp'}.</p>}
    <p className="hjmuted">{s.state === 'wait' ? 'Не получается? Выбери другой день:' : 'Целый день работы на объекте с куратором. Куратор подтвердит день и пришлёт время и адрес.'}</p>
    <div className="hjdays">{(s.days || []).map(d => <button key={d} className={d === s.day ? 'on' : ''} disabled={!!busy} onClick={() => pick(d)}>
      {busy === d ? '…' : new Date(d + 'T00:00:00').toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' })}</button>)}</div>
    {err && <p className="hjerr">{err}</p>}{tg}</>)
  if (s.step === 'trial') return box(<>
    <span className="hjtag">Пробный день</span>
    <h1>{hi}ждём тебя на пробный день</h1>
    <div className="hjrows">
      <div><span>Когда</span><b>{s.day ? fmtDay(s.day) : 'дату сообщим'}{s.time ? `, ${s.time}` : ''}</b></div>
      {s.place && <div><span>Куда</span><b>{s.place}</b></div>}
      {s.who && <div><span>Встретит</span><b>{s.who}{s.who_phone ? <> · <a href={`tel:${s.who_phone}`}>{s.who_phone}</a></> : null}</b></div>}
      {s.bring && <div><span>Взять с собой</span><b>{s.bring}</b></div>}
    </div>
    <p className="hjmuted">Весь день работаешь с куратором на объекте. Пробный день оплачивается, если тебя возьмут в команду.
      Не получается прийти — сразу напиши или позвони{s.who ? ` ${s.who.split(' ')[0]}` : ''}.</p>{tg}</>)
  if (s.step === 'meet') return box(<><span className="hjtag">Собеседование</span><h1>{hi}ждём на разговор</h1>
    <div className="hjrows"><div><span>Когда</span><b>{s.day ? fmtDay(s.day) : 'время согласуем'}</b></div></div>
    <p className="hjmuted">Время и место пришлём {j.bot ? 'в Telegram' : 'в WhatsApp'}.</p>{tg}</>)
  if (s.step === 'hired') return box(<><span className="hjtag">Ты в команде</span><h1>{hi}добро пожаловать в ARTGAME</h1>
    <p className="hjmuted">Открой бот ARTGAME в Telegram, нажми «Старт», потом «ARTGAME» внизу и введи имя и этот номер: {s.phone}. Дальше приложение покажет правила и первые шаги.</p></>)
  if (s.step === 'base') return box(<><h1>{hi}спасибо за анкету</h1><p className="hjmuted">Сейчас позвать не можем, но анкета осталась у нас. Когда появится место, напишем.</p></>)
  return box(<><h1>{hi}анкета у нас</h1><p className="hjmuted">Посмотрим работы и ответим {j.bot ? 'в Telegram' : 'в WhatsApp'}.</p>{tg}</>)
}

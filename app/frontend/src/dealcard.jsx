import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { SalesSpend } from './salesexp.jsx'
import { Embed } from './places.jsx'
import { CityPicker, Copy, Sheet, WaitSheet, cityBase } from './ui.jsx'
import { CallOutcome, Contact, Feed, Skeleton, bxLink, cleanTitle, dt, money, strip, usePortal } from './crm.jsx'
import { leftText } from './projects.jsx'
import { FillBar, FillSheet, LOCK_DOCS, LOCK_KP, Locked, anketaKey, lockFor, missingFor } from './fill.jsx'

// Карточка сделки = единственное рабочее поле МОП (HEAD 06.11, вариант А). Тёмная шапка с шагами, нажатие на шаг открывает
// его панель: Клиент → Расчёт → КП → Договор → Оплата → В работе. Расчёт считает сервер по «Значениям» и пишет в Битрикс;
// КП и документы — панель рабочего места с подставленной сделкой и расчётом; скрипты и заметки — во всплывающих окнах.
const LEVELS = { easy: 'Лёгкий', medium: 'Средний', hard: 'Сложный', author: 'Авторский' }
const FIX = { lite: 'Лёгкий', hard: 'Сложный', excl: 'Эксклюзив' }
const SERVICES = [['mural', 'Роспись'], ['print', 'Печать'], ['fix', 'Фикс-прайс'], ['bulk', 'Покраска']]
const EXTRAS = [['urgent', 'Срочность'], ['height', 'Высота'], ['night', 'Ночь'], ['lacquer', 'Лак']]
const DESIGNS = ['XS', 'S', 'M', 'L', 'XL']
const PLACES = [['base', 'Астана / Шымкент'], ['near', '150–200 км'], ['far', 'Другой город']]
const POSTPONED = 'UC_VCP4VO'
const KP_ON = new Set(['PREPARATION', 'UC_VZFPUP', 'UC_YV66BV', 'UC_1EXUAC', 'FINAL_INVOICE', 'UC_AV00QK', 'UC_BMKDS4'])
const DOG_ON = new Set(['FINAL_INVOICE', 'UC_AV00QK', 'UC_BMKDS4'])
const WORK_ON = new Set(['UC_AV00QK', 'UC_BMKDS4', 'WON'])
const STEPS = [['client', 'Клиент'], ['calc', 'Расчёт'], ['kp', 'КП'], ['docs', 'Договор'], ['pay', 'Оплата'], ['work', 'В работе']]
// скрипты рабочего места по шагам алгоритма (rm_extra.js STEP_SCR) → панели карточки
const STEP_SCR = { '01': ['С1', 'С2', 'С3', 'Ж1', 'Ж2'], '03': ['С4', 'С5', 'С8', 'Ж3', 'Ж4', 'Ж5'], '05': ['С6', 'С7', 'Д1', 'Д2', 'Д3'], '06': ['С8', 'С26', 'С13', 'Ж16'],
  '07': ['Д4', 'Д5', 'Д6', 'Д7'], '08': ['Д7', 'Д8'], '09': ['С17', 'С23', 'С24', 'Ж17', 'Ж18'], '12': ['С25'] }
const PANEL_ALGO = { client: ['01', '03'], calc: ['05'], kp: ['06'], docs: ['09', '07'], pay: ['09'], work: ['12'], hist: ['12'] }
const tomorrow = () => new Date(Date.now() + 86400000).toISOString().slice(0, 10)
const autoDesign = m2 => m2 < 30 ? 'S' : m2 < 200 ? 'M' : m2 < 1000 ? 'L' : 'XL'
const MAT = [['ARTGAME_Price_2026_phone.pdf', 'Прайс 2026', 'для WhatsApp'], ['ARTGAME_Price_paintings_2026_phone.pdf', 'Прайс картин', 'для WhatsApp'],
  ['ARTGAME_Catalog_FixPrice_2026_phone.pdf', 'Каталог фикс-прайса', 'рисунки 01–32'], ['ARTGAME_Object_requirements_phone.pdf', 'Подготовка объекта', 'стены, доступ, условия'],
  ['ARTGAME_Warranty_care_phone.pdf', 'Гарантия и уход', 'срок, что покрывает'], ['ARTGAME_Company_card.pdf', 'Карточка компании', 'наши реквизиты']]

function steps(d, calc) {
  const has = t => d.files.some(f => f.title.startsWith(t))
  return [['client', !!(d.client?.phone || d.client?.name)], ['calc', !!(calc?.out?.total) || !!d.norm.shifts], ['kp', KP_ON.has(d.stage) || has('КП')],
    ['docs', DOG_ON.has(d.stage) || has('Договор')], ['pay', d.pay.received > 0], ['work', WORK_ON.has(d.stage)]]
}

let scriptsCache = null
function useScripts() {
  const [s, setS] = useState(scriptsCache)
  useEffect(() => { if (!scriptsCache) api('/bx/scripts').then(r => { scriptsCache = r; setS(r) }, () => setS({ scr: { p1: [], p2: [] }, algo: { steps: [] } })) }, [])
  return s
}
const allScr = s => [...(s?.scr?.p1 || []), ...(s?.scr?.p2 || [])].flatMap(([, items]) => items)

// Скрипты шага во всплывающем окне: русский / казахский, каждая реплика копируется одной кнопкой.
function Scripts({ codes, title, onClose, algoStep }) {
  const s = useScripts()
  const [lang, setLang] = useState(() => { try { return localStorage.getItem('ag-rm-lang') || 'ru' } catch { return 'ru' } })
  const byCode = Object.fromEntries(allScr(s).map(x => [x.c, x]))
  const list = codes.map(c => byCode[c]).filter(Boolean)
  const step = s?.algo?.steps?.find(x => x.n === algoStep)
  return <Sheet title={title} onClose={onClose}>
    {step && <div className="hint"><div><b>Шаг {+step.n}. {step.title}</b><br />Результат: {step.result}{step.bx ? <><br />Битрикс: {step.bx}</> : null}</div></div>}
    <div className="segf"><button className={lang === 'ru' ? 'on' : ''} onClick={() => { setLang('ru'); try { localStorage.setItem('ag-rm-lang', 'ru') } catch { /* */ } }}>Русский</button>
      <button className={lang === 'kz' ? 'on' : ''} onClick={() => { setLang('kz'); try { localStorage.setItem('ag-rm-lang', 'kz') } catch { /* */ } }}>Қазақша</button></div>
    {!s && <Skeleton n={3} />}
    {s && !list.length && <p className="muted">Для этого шага готовых реплик нет — см. учебник во вкладке «Учёба».</p>}
    {list.map(x => { const t = lang === 'kz' && x.kz ? x.kz : x.ru
      return <div key={x.c} className="scr"><div><span className="code">{x.c}</span><b>{x.s}</b></div><div className="st">{t}</div>
        {x.n && <div className="sn">{x.n}</div>}<div className="dealbtns"><Copy text={t} />{lang === 'kz' && !x.kz && <span className="small muted">только на русском</span>}</div></div> })}
  </Sheet>
}

// Перевод стадии: отказ — только с причиной из списка (HEAD 06.11, 8 причин) и строкой комментария; «Отложено» — с датой возврата.
function StageSheet({ d, stages, onClose, onDone, onFill }) {
  const [stage, setStage] = useState(d.stage)
  const [code, setCode] = useState('')
  const [reason, setReason] = useState('')
  const [until, setUntil] = useState('')
  const [reasons, setReasons] = useState([])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api('/bx/reasons').then(setReasons, () => {}) }, [])
  const sel = stages.find(s => s.id === stage)
  const fail = ['failure', 'apology'].includes(sel?.semantic)
  const miss = !fail && stage !== d.stage && stage !== POSTPONED ? missingFor(d.fill, d.stage, stage) : []
  const ok = stage !== d.stage && (!fail || code) && (stage !== POSTPONED || until) && !miss.length
  const send = () => { setBusy(true); api(`/bx/deals/${d.id}/stage`, { method: 'POST', body: { stage, reason: reason || null, reason_code: fail ? code : null, until: stage === POSTPONED ? until : null } })
    .then(r => onDone(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Стадия записана в Битрикс.'), e => { setErr(e.message); setBusy(false) }) }
  return <Sheet title="Стадия сделки" onClose={onClose}>
    <select value={stage} onChange={e => setStage(e.target.value)}>{stages.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
    {fail && <>
      <p className="small muted">Причина отказа — одна из списка, к ней строка комментария. «Прочее» нет нарочно: так отчёт покажет, что чинить.</p>
      <div className="chips">{reasons.map(r => <button key={r.code} className={code === r.code ? 'on' : ''} onClick={() => setCode(r.code)}>{r.name}</button>)}</div>
      <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Комментарий: что именно сказал клиент" />
    </>}
    {stage === POSTPONED && <>
      <label>Вернуться к сделке<input type="date" value={until} min={tomorrow()} onChange={e => setUntil(e.target.value)} /></label>
      <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Почему отложили" />
      <p className="small muted">В Битриксе появится задача с этой датой, бот напомнит утром.</p></>}
    {!fail && stage !== POSTPONED && stage !== d.stage && <input value={reason} onChange={e => setReason(e.target.value)} placeholder="Комментарий (по желанию)" />}
    {!!miss.length && <div className="lockbox"><b>🔒 На эту стадию нельзя, пока не заполнено:</b>
      <div>{miss.map(m => <span key={m} className="miss">{m}</span>)}</div>
      <button className="mini" onClick={onFill}>Заполнить карточку</button></div>}
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
    <button disabled={!ok || busy} onClick={send}>Перевести</button>
  </Sheet>
}

function NoteSheet({ d, onClose, onDone, initial = '' }) {
  const [text, setText] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const send = () => { setBusy(true); api(`/bx/deals/${d.id}/note`, { method: 'POST', body: { text } }).then(r => onDone(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Заметка записана в ленту сделки.'), e => { setErr(e.message); setBusy(false) }) }
  return <Sheet title="Заметка в сделку" onClose={onClose}>
    <textarea rows={4} value={text} onChange={e => setText(e.target.value)} placeholder="Что важно помнить по этой сделке" autoFocus />
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
    <button disabled={!text.trim() || busy} onClick={send}>Записать</button>
  </Sheet>
}

// Объединённый расчёт: цена клиенту + срок и состав одной формой. Считает сервер (POST /price), «Записать в сделку» — /price/save.
function Calc({ d, saved, onSaved }) {
  const svc0 = /печат/i.test(d.service || '') ? 'print' : 'mural'
  const [f, setF] = useState(() => saved?.in || { service: svc0, area: d.area || '', level: d.level || 'medium', design: null, extras: [], outdoor: false, place: 'base', cash: 0, qty: 1 })
  const [r, setR] = useState(saved?.out || null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')
  const t = useRef(null)
  useEffect(() => {
    if (!(+f.area > 0) && f.service !== 'fix') { setR(null); return undefined }
    clearTimeout(t.current)
    t.current = setTimeout(() => api(`/bx/deals/${d.id}/price`, { method: 'POST', body: { ...f, area: +f.area || 0, cash: +f.cash || 0 } }).then(x => { setR(x); setErr('') }, e => setErr(e.message)), 250)
    return () => clearTimeout(t.current)
  }, [f])
  const set = p => setF({ ...f, ...p })
  const tog = k => set({ extras: f.extras.includes(k) ? f.extras.filter(x => x !== k) : [...f.extras, k] })
  const save = () => { setBusy(true); setMsg(''); api(`/bx/deals/${d.id}/price/save`, { method: 'POST', body: { ...f, area: +f.area || 0, cash: +f.cash || 0 } })
    .then(x => onSaved(x.bx === 'off' ? 'Расчёт сохранён, в Битрикс не записан (ключ записи не задан).' : 'Записано в сделку: сумма, площадь' + (x.norm_fields ? ', смены и срок.' : '. Полей для смен и срока в Битриксе ещё нет — задание Кодексу.')), e => setMsg('Не записалось: ' + e.message)).finally(() => setBusy(false)) }
  const n = r?.norm || {}
  const isArea = f.service !== 'fix'
  return <div className="card">
    <div className="panelhead"><h3>Расчёт</h3><span className="small muted">{saved ? `записан ${dt(saved.at)}` : 'по «Значениям» сейчас'}</span></div>
    <div className="segf">{SERVICES.map(([k, name]) => <button key={k} className={f.service === k ? 'on' : ''} onClick={() => set({ service: k, design: null })}>{name}</button>)}</div>
    {isArea && <label>Площадь, м²<input type="number" min="1" inputMode="decimal" value={f.area} onChange={e => set({ area: e.target.value, design: null })} placeholder="60" /></label>}
    {f.service === 'mural' && <><label>Сложность</label><div className="chips">{Object.entries(LEVELS).map(([k, v]) => <button key={k} className={f.level === k ? 'on' : ''} onClick={() => set({ level: k })}>{v}</button>)}</div></>}
    {f.service === 'fix' && <><label>Рисунок</label><div className="chips">{Object.entries(FIX).map(([k, v]) => <button key={k} className={f.level === k ? 'on' : ''} onClick={() => set({ level: k })}>{v}</button>)}</div>
      <label>Количество работ<input type="number" min="1" value={f.qty} onChange={e => set({ qty: +e.target.value || 1 })} /></label></>}
    {(f.service === 'mural' || f.service === 'print') && <>
      <label>Дизайн <span className="muted">· по площади {autoDesign(+f.area || 0)}, другую — только по решению HEAD</span></label>
      <div className="chips">{DESIGNS.map(k => <button key={k} className={(f.design || autoDesign(+f.area || 0)) === k ? 'on' : ''} onClick={() => set({ design: k })}>{k}</button>)}</div>
      <label>Надбавки и условия</label>
      <div className="chips">{EXTRAS.map(([k, v]) => <button key={k} className={f.extras.includes(k) ? 'on' : ''} onClick={() => tog(k)}>{v} +10%</button>)}
        <button className={f.outdoor ? 'on' : ''} onClick={() => set({ outdoor: !f.outdoor })}>Улица</button></div></>}
    {isArea && <><label>Где объект</label><div className="chips">{PLACES.map(([k, v]) => <button key={k} className={f.place === k ? 'on' : ''} onClick={() => set({ place: k })}>{v}</button>)}</div></>}
    <label>Скидка за наличные, % (до 15)<input type="number" min="0" max="15" value={f.cash} onChange={e => set({ cash: e.target.value })} /></label>
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
    {r && <>
      <div className="lines">{r.lines.map(([c, s, v], i) => <div key={i} className={c.replace('ln', '').trim()}><span>{s}</span><span>{typeof v === 'number' ? (v < 0 ? '−' + money(-v) : money(v)) : v}</span></div>)}</div>
      <div className="total"><span>{r.no_vat ? 'Итого по акции, без НДС' : 'Итого с НДС'}</span><b>{money(r.total)}</b></div>
      <div className="two">
        <div><h4>Клиенту</h4><div className="kv">
          <div><span className="muted small">Аванс {r.pay.prepay_pct}%</span><b>{money(r.pay.prepay)}</b></div>
          <div><span className="muted small">Остаток</span><b>{money(r.pay.rest)}</b></div>
          {r.dprice ? <div><span className="muted small">Дизайн {r.design}, 100% вперёд</span><b>{money(r.dprice)}</b></div> : null}
          <div><span className="muted small">{r.pay.vat_included ? 'В том числе НДС' : 'Если нужен счёт с НДС'}</span><b>{money(r.pay.vat)}</b></div>
          {r.rate ? <div><span className="muted small">За м²</span><b>{money(r.rate)}</b></div> : null}
        </div></div>
        <div><h4>Команде</h4>{n.shifts ? <div className="kv">
          <div><span className="muted small">Смен по норме</span><b>{n.shifts}</b></div>
          <div><span className="muted small">Художников</span><b>{n.crew}</b></div>
          <div><span className="muted small">Срок клиенту</span><b>{n.client} раб. дн.</b></div>
          <div><span className="muted small">Подготовка + работа</span><b>{n.prep} + {n.work} дн.</b></div>
          {n.ink ? <div><span className="muted small">Чернила</span><b>{n.ink} мл</b></div> : null}
        </div> : <p className="small muted">Срок и состав считаются для росписи и печати по площади.</p>}</div>
      </div>
      {r.flags.map(([c, t], i) => <div key={i} className={'flag ' + c}>{t}</div>)}
      <div className="copybox">{r.ladder}</div>
      <div className="dealbtns wrapbtns"><Copy text={r.ladder} label="Скопировать лестницу цены" /><Copy text={r.client_text} label="Скопировать текст клиенту" /></div>
      <button disabled={busy || !r.total} onClick={save}>{saved ? 'Записать заново в сделку' : 'Записать в сделку'}</button>
      {msg && <p className="small muted">{msg}</p>}
      <p className="small muted">В сделку уходят сумма, площадь, сложность, смены, состав и срок; в ленту — короткий расчёт. КП и договор возьмут эти цифры сами.</p>
    </>}
    {!r && !err && <p className="small muted">Укажите площадь — цена, аванс, смены и срок появятся сразу.</p>}
  </div>
}

// Квалификация клиента (шаг «Клиент»): город, услуга, площадь, адрес → в сделку.
function Qualify({ d, onDone }) {
  const [dict, setDict] = useState(null)
  const [f, setF] = useState({ cityName: d.city || '', city: '', service: '', area: d.area || '', address: d.address || '' })
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')
  useEffect(() => { api('/bx/dict').then(x => { setDict(x); const s = x.services.find(s => s.name === d.service); setF(v => ({ ...v, service: s?.id || '' })) }, () => setDict({ cities: [], services: [] })) }, [])
  const changed = (f.city && f.cityName !== d.city) || (+f.area || 0) !== (d.area || 0) || (f.address || '') !== (d.address || '') || (f.service && (dict?.services.find(s => s.id === f.service)?.name || '') !== (d.service || ''))
  const save = () => { setBusy(true); api(`/bx/deals/${d.id}/fields`, { method: 'POST', body: { city: f.city || null, service: f.service || null, area: +f.area || null, address: f.address || null } })
    .then(r => { setMsg(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Записано в Битрикс.'); onDone() }, e => setMsg('Не записалось: ' + e.message)).finally(() => setBusy(false)) }
  return <>
    <h3>Что нужно для расчёта</h3>
    <CityPicker cities={dict?.cities || []} value={f.city || (dict?.cities || []).find(c => c.name === d.city)?.id || ''} need={!d.city && !f.city} onPick={(id, name) => setF({ ...f, city: id, cityName: name })} />
    <label>Услуга<select value={f.service} onChange={e => setF({ ...f, service: e.target.value })}><option value="">—</option>{(dict?.services || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
    <label>Площадь, м²<input type="number" min="1" inputMode="decimal" value={f.area} onChange={e => setF({ ...f, area: e.target.value })} /></label>
    <label>Адрес объекта<input value={f.address} onChange={e => setF({ ...f, address: e.target.value })} placeholder="Город, улица, дом" /></label>
    <button className="ghost" disabled={!changed || busy} onClick={save}>Сохранить в Битрикс</button>
    {msg && <p className="small muted">{msg}</p>}
  </>
}

function Materials({ place, d, portal }) {
  if (!place) return null
  const base = place.url.replace(/index\.html$/, '')
  const bx = bxLink(portal, 'deal', d.id)
  const send = f => { window.open(base + 'files/' + f, '_blank', 'noopener'); if (bx) setTimeout(() => window.open(bx, '_blank', 'noopener'), 300) }
  return <div className="card"><h3>Материалы клиенту</h3>
    <p className="small muted">«Отправить» скачивает файл и открывает карточку клиента в Битриксе — прикрепите его в чат. С личных номеров не пишем.</p>
    {MAT.map(([f, title, sub]) => <div key={f} className="mat"><div><b>{title}</b><div className="small muted">{sub}</div></div>
      <div className="dealbtns"><button className="mini" onClick={() => send(f)}>Отправить</button><a className="btn ghost mini" href={base + 'files/' + f} target="_blank" rel="noreferrer" aria-label="Скачать">↓</a></div></div>)}
  </div>
}

function WorkPanel({ d, portal }) {
  const [p, setP] = useState(null)
  useEffect(() => { api('/bx/projects').then(r => setP(r.projects.find(x => x.id === d.id) || false), () => setP(false)) }, [d.id])
  return <div className="card"><h3>В работе</h3>
    {p === null && <Skeleton n={1} />}
    {p === false && <p className="small muted">{WORK_ON.has(d.stage) ? 'Проект пока не виден во вкладке «Проекты».' : 'Сделка ещё не переведена в работу. После подписанного договора и аванса переведите стадию — проект появится у всей команды во вкладке «Проекты».'}</p>}
    {p && <>
      <div className="kv">
        <div><span className="muted small">Старт</span><b>{p.start ? p.start.split('-').reverse().join('.') : '—'}</b></div>
        <div><span className="muted small">Сдача</span><b>{p.due ? p.due.split('-').reverse().join('.') : 'срок не задан'}</b></div>
        <div><span className="muted small">Осталось</span><b className={p.state === 'late' ? 'left late' : ''}>{leftText(p)}</b></div>
        <div><span className="muted small">Смен</span><b>{p.done.shifts}{p.norm.shifts ? ` из ${p.norm.shifts}` : ''}</b></div>
      </div>
      {p.people.length ? <p className="small">На объекте: {p.people.join(', ')}</p> : <p className="small muted">Смен за последние дни не отмечено.</p>}
    </>}
    <p className="small muted">Передача куратору — заметкой в сделку; дата старта называется клиенту только после подтверждения загрузки (скрипт С23).</p>
  </div>
}

// Название сделки (HEAD 06.11): не пишется руками — собирается из «Объекта» и «Города»: «1237 · ШКОЛА №12 — ШАХТИНСК».
function TitleSheet({ d, onClose, onDone }) {
  const [dict, setDict] = useState(null)
  const [obj, setObj] = useState(d.object || '')
  const [city, setCity] = useState({ id: '', name: d.city || '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  useEffect(() => { api('/bx/dict').then(x => { setDict(x); const c = x.cities.find(c => c.name === d.city); if (c) setCity({ id: c.id, name: c.name }) }, () => setDict({ cities: [] })) }, [])
  const cityId = city.id && city.name !== d.city ? city.id : null
  const ok = obj.trim() && (obj.trim() !== (d.object || '') || cityId)
  const preview = `${d.id} · ${obj.trim().toUpperCase()}${city.name ? ' — ' + cityBase(city.name).toUpperCase() : ''}`
  const send = () => { setBusy(true); api(`/bx/deals/${d.id}/fields`, { method: 'POST', body: { object: obj.trim(), city: cityId } })
    .then(r => onDone(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Название записано в Битрикс.'), e => { setErr(e.message); setBusy(false) }) }
  return <Sheet title="Название сделки" onClose={onClose}>
    <p className="small muted">Название собирается само из объекта и города — так сделку найдёт любой в Битриксе и в папках Диска.</p>
    <label>Объект<input value={obj} onChange={e => setObj(e.target.value)} placeholder="«Школа №12», «Кофейня Daily»" autoFocus /></label>
    {dict ? <CityPicker cities={dict.cities} value={city.id} onPick={(id, name) => setCity({ id, name })} need={!city.name} /> : <Skeleton n={1} />}
    {obj.trim() && <div className="titleprev">Будет: <b>{preview}</b></div>}
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
    <button disabled={!ok || busy} onClick={send}>{busy ? 'Записываю…' : 'Записать'}</button>
  </Sheet>
}

// Сделка без «Контакта» (перевели в Битриксе «Сделка» без «Контакт»): телефон берём из лида, контакт создаём одной кнопкой.
function ContactFix({ d, onDone }) {
  const c = d.client || {}
  const [open, setOpen] = useState(false)
  const [f, setF] = useState({ name: c.name || '', phone: c.phone || '' })
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  if (!c.no_contact) return null
  const send = body => { setBusy(true); setErr(''); api(`/bx/deals/${d.id}/contact`, { method: 'POST', body })
    .then(r => onDone(r.bx === 'off' ? 'Сохранено в журнал, в Битрикс не записано.' : 'Контакт создан и привязан к сделке.'), e => { setErr(e.message); setBusy(false) }) }
  return <div className="warnbox">
    <b>У сделки нет контакта{c.phone_from === 'lead' ? ' — телефон взят из лида' : ''}.</b>
    <p className="small">Без контакта звонок и WhatsApp из сделки не работают, а в договор не попадёт клиент.</p>
    {!open ? <div className="dealbtns wrapbtns">
      <button className="mini" disabled={busy} onClick={() => c.phone ? send({ name: c.name || null, phone: c.phone }) : setOpen(true)}>{busy ? 'Создаю…' : c.phone ? `Создать контакт (${c.phone})` : 'Создать контакт'}</button>
      {c.phone && <button className="ghost mini" onClick={() => setOpen(true)}>Другой номер</button>}</div>
      : <div className="dealedit">
        <input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Имя клиента" />
        <input value={f.phone} type="tel" inputMode="tel" onChange={e => setF({ ...f, phone: e.target.value })} placeholder="+7 7__ ___ __ __" />
        <div className="dealbtns"><button className="mini" disabled={busy || f.phone.replace(/\D/g, '').length < 10} onClick={() => send({ name: f.name.trim() || null, phone: f.phone.trim() })}>Создать контакт</button>
          <button className="ghost mini" onClick={() => setOpen(false)}>Отмена</button></div></div>}
    {err && <p className="small" style={{ color: 'var(--hot)' }}>{err}</p>}
  </div>
}

export function DealCard({ id, back, place }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [stages, setStages] = useState([])
  const [calc, setCalc] = useState(undefined)
  const [panel, setPanel] = useState(null)
  const [sheet, setSheet] = useState(null)   // {kind: call|stage|note|say, ...}
  const [msg, setMsg] = useState('')
  const portal = usePortal()
  const load = fresh => api(`/bx/deals/${id}/full${fresh ? '?fresh=1' : ''}`).then(setD, e => setErr(e.message))
  const loadCalc = () => api(`/bx/deals/${id}/calc`).then(c => setCalc(c && c.out ? c : null), () => setCalc(null))
  useEffect(() => { load(false); loadCalc(); api('/bx/stages').then(setStages, () => {}) }, [id])
  const said = t => { setSheet(null); setMsg(t); load(true); setTimeout(() => setMsg(''), 5000) }
  if (err) return <div className="card"><a onClick={back}>← назад</a><p className="muted">{err}</p></div>
  if (!d || calc === undefined) return <Skeleton n={3} />
  const c = d.client || {}
  const st = steps(d, calc)
  const nextI = st.findIndex(x => !x[1])
  const cur = panel || (nextI >= 0 ? st[nextI][0] : 'work')
  const name = k => STEPS.find(s => s[0] === k)?.[1] || 'История'
  const NEXT = { client: 'Заполнить и позвонить', calc: 'Посчитать цену и срок', kp: 'Собрать КП', docs: 'Договор и счёт', pay: 'Оплата', work: 'Проект' }
  const say = () => setSheet({ kind: 'say' })
  const algo = PANEL_ALGO[cur] || ['01']
  const codes = [...new Set(algo.flatMap(n => STEP_SCR[n] || []))]
  const kpItem = calc?.kp
  const lockKP = lockFor(d.fill, LOCK_KP), lockDocs = lockFor(d.fill, LOCK_DOCS)
  const fillIt = () => setSheet({ kind: 'fill' })
  const onDoc = x => { load(true); if (x?.held?.length) { setMsg('Файл в сделке, но стадия не сменилась — не хватает: ' + x.held.join(', ')); setTimeout(() => setMsg(''), 8000) } }
  let anketa = ''
  try { anketa = localStorage.getItem(anketaKey(d.id)) || '' } catch { /* без памяти */ }
  const ds = calc || anketa ? { ...(calc ? { total: calc.out.total, area: +calc.in.area || 0, prepay: calc.out.pay?.prepay, adv: calc.out.pay?.prepay_pct, days: calc.out.norm?.client } : {}), anketa } : null
  return <>
    <div className="hero">
      <a className="back" onClick={back}>← к сделкам</a>
      <h2>№ {d.id} · {cleanTitle(d.title, d.id)} <button className="pencil" aria-label="Изменить название" onClick={() => setSheet({ kind: 'title' })}>✎</button></h2>
      <span className="tag">{d.stage_name}</span>{d.manager && <span className="tag">{d.manager}</span>}
      <div className="kv">
        <div><span className="muted small">Сумма</span><b>{money(d.sum)}</b></div>
        <div><span className="muted small">Площадь</span><b>{d.area ? d.area + ' м²' : '—'}</b></div>
        <div><span className="muted small">Услуга</span><b>{d.service || '—'}</b></div>
        <div><span className="muted small">Город</span><b>{d.city || '—'}</b></div>
      </div>
      <Contact phone={c.phone} name={[c.name, d.contact && d.contact !== c.name ? d.contact : ''].filter(Boolean).join(' · ')} entity="deal" id={d.id} />
      <ContactFix key={d.modified} d={d} onDone={said} />
      <div className="steps">{st.map(([k, ok], i) => <div key={k} className={(ok ? 'done' : i === nextI ? 'next' : '') + (cur === k ? ' cur' : '')} onClick={() => setPanel(k)}><i />{name(k)}</div>)}</div>
      <FillBar fill={d.fill} onOpen={() => setSheet({ kind: 'fill' })} />
      <div className="nextstep">{nextI >= 0 ? <><div><span className="small muted">Следующий шаг</span><b>{name(st[nextI][0])}</b></div>
        <button className="mini" onClick={() => setPanel(st[nextI][0])}>{NEXT[st[nextI][0]]}</button></>
        : <div><b>Все шаги пройдены</b><span className="small muted">проект в работе</span></div>}</div>
      <div className="dealbtns wrapbtns">
        <button className="ghost" onClick={() => setSheet({ kind: 'call' })}>Итог звонка</button>
        <button className="ghost" onClick={() => setSheet({ kind: 'wait' })}>Жду ответа</button>
        <button className="ghost" onClick={say}>Сообщение</button>
        <button className="ghost" onClick={() => setSheet({ kind: 'fill' })}>Заполнить карточку</button>
        <button className="ghost" onClick={() => setSheet({ kind: 'note' })}>Заметка</button>
        <button className="ghost" onClick={() => setSheet({ kind: 'stage' })}>Стадия</button>
        <button className={'ghost' + (cur === 'hist' ? ' on' : '')} onClick={() => setPanel('hist')}>История</button>
      </div>
    </div>
    {msg && <div className="toast">{msg}</div>}

    {cur === 'client' && <div className="card">
      <div className="panelhead"><h3>Клиент</h3><button className="ghost mini" onClick={say}>Скрипты шага</button></div>
      <div className="hint"><div><b>Шаг 1–3.</b> Ответить в течение 30 минут, узнать помещение, город, площадь и фото стены; назвать ориентир по лестнице цены; договориться о следующем касании.</div></div>
      {portal && <a className="btn" href={bxLink(portal, 'deal', d.id)} target="_blank" rel="noreferrer" style={{ display: 'block', marginBottom: 10 }}>Позвонить · WhatsApp в Битриксе</a>}
      <Qualify key={d.modified} d={d} onDone={() => load(true)} />
    </div>}
    {cur === 'calc' && <Calc key={calc?.at || 'new'} d={d} saved={calc} onSaved={t => { loadCalc(); said(t) }} />}
    {cur === 'kp' && <>
      <div className="card">
        <div className="panelhead"><h3>Коммерческое предложение</h3><button className="ghost mini" onClick={say}>Скрипты шага</button></div>
        {calc ? <p className="small muted">Позиция из расчёта ({money(calc.out.total)}) уже в КП, клиент и сделка подставлены. Проверьте, скачайте PDF — файл ляжет в сделку Битрикса, стадия сменится на «Отправка КП».</p>
          : <p className="small why">Сначала сделайте расчёт — тогда КП соберётся без ввода цифр. <a onClick={() => setPanel('calc')}>К расчёту</a></p>}
        {lockKP.length ? <Locked what="КП" miss={lockKP} onFill={fillIt} onCalc={() => setPanel('calc')} />
          : <Embed place={place} view="kp" dealId={d.id} kp={kpItem} onDoc={onDoc} />}
      </div>
      <Materials place={place} d={d} portal={portal} />
    </>}
    {cur === 'docs' && <>
      <div className="card">
        <div className="panelhead"><h3>Договор, счёт, акт</h3><button className="ghost mini" onClick={say}>Скрипты шага</button></div>
        <p className="small muted">{calc ? `Сумма ${money(calc.out.total)} и аванс ${money(calc.out.pay.prepay)} — из расчёта; ` : ''}клиент и реквизиты — из Битрикса (если их там нет, вставьте из анкеты). Скачанный файл ложится в сделку, стадия — «Отправка счёта/договора».</p>
        {lockDocs.length ? <Locked what="Договор и счёт" miss={lockDocs} onFill={fillIt} onCalc={() => setPanel('calc')} />
          : <Embed place={place} view="docs" dealId={d.id} ds={ds} onDoc={onDoc} />}
      </div>
      {!!d.files.length && <div className="card"><h3>Документы в сделке</h3>
        {d.files.map((f, i) => <div key={i} className="row"><span>{f.title}</span>{f.url ? <a href={f.url} target="_blank" rel="noreferrer">открыть</a> : <span className="muted small">в Битриксе</span>}</div>)}</div>}
    </>}
    {cur === 'pay' && <>
      <div className="card"><h3>Оплата</h3>
        <div className="kv">
          <div><span className="muted small">Поступило</span><b>{money(d.pay.received)}</b></div>
          <div><span className="muted small">Долг</span><b>{money(d.pay.debt)}</b></div>
          {calc && <div><span className="muted small">Аванс по расчёту</span><b>{money(calc.out.pay.prepay)}</b></div>}
          {d.pay.next && <div><span className="muted small">Ближайший платёж</span><b>{d.pay.next.slice(0, 10)}</b></div>}
        </div>
        <p className="small muted">Поступления отмечает HEAD, сервер считает долг. Когда аванс пришёл и договор подписан — переведите сделку в работу и передайте куратору.</p>
        <div className="dealbtns wrapbtns">
          <button className="mini" onClick={() => setSheet({ kind: 'stage' })}>Перевести в работу</button>
          <button className="ghost mini" onClick={() => setSheet({ kind: 'note', text: 'Передаю куратору: аванс получен, договор подписан. Старт — после подтверждения загрузки.' })}>Передать куратору</button>
          <button className="ghost mini" onClick={say}>Скрипты шага</button>
        </div>
      </div>
      <SalesSpend dealId={d.id} />
    </>}
    {cur === 'work' && <WorkPanel d={d} portal={portal} />}
    {cur === 'hist' && <>
      {d.comments && <div className="card"><h3>Комментарий сделки</h3><p className="small">{strip(d.comments)}</p></div>}
      <Feed items={d.feed} />
      {!!d.history.length && <div className="card"><h3>Стадии</h3>
        {d.history.map((h, i) => <div key={i} className="row"><span>{h.stage}</span><span className="muted small">{dt(h.at)}</span></div>)}</div>}
      <SalesSpend dealId={d.id} />
    </>}

    {sheet?.kind === 'call' && <Sheet title="Итог звонка" onClose={() => setSheet(null)}><CallOutcome path={`/bx/deals/${id}`} auto done={() => said('Итог звонка записан.')} /></Sheet>}
    {sheet?.kind === 'title' && <TitleSheet d={d} onClose={() => setSheet(null)} onDone={said} />}
    {sheet?.kind === 'wait' && <WaitSheet api={api} path={`/bx/deals/${id}`} onClose={() => setSheet(null)} onDone={said} />}
    {sheet?.kind === 'stage' && <StageSheet d={d} stages={stages} onClose={() => setSheet(null)} onDone={said} onFill={() => setSheet({ kind: 'fill' })} />}
    {sheet?.kind === 'fill' && <FillSheet d={d} onClose={() => setSheet(null)} onDone={said} />}
    {sheet?.kind === 'note' && <NoteSheet d={d} initial={sheet.text} onClose={() => setSheet(null)} onDone={said} />}
    {sheet?.kind === 'say' && <Scripts codes={codes} algoStep={algo[0]} title={`Скрипты: ${name(cur)}`} onClose={() => setSheet(null)} />}
  </>
}

// «Мой месяц»: выигранные сделки месяца из Битрикса, выручка без НДС, ступень и % по «Значениям» (pay.mop.*). HEAD видит всех.
const MONTHS = ['январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const ymName = ym => { const [y, m] = ym.split('-'); return `${MONTHS[+m - 1]} ${y}` }
const ymShift = (ym, k) => { const [y, m] = ym.split('-').map(Number); const d = new Date(y, m - 1 + k, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}` }
// План месяца (HEAD 06.11): шкала до верхней ступени, отметки 2/7/15 млн из «Значений», темп к концу месяца.
const mln = x => x >= 1e6 ? `${(+(x / 1e6).toFixed(1)).toLocaleString('ru-RU')} млн` : money(x)
function Plan({ m }) {
  const co = m.company, steps = m.steps.filter(s => s.from)
  if (!steps.length) return <p className="small muted">Ступени процента МОП не заданы в «Значениях».</p>
  const top = steps[steps.length - 1].from * 1.15
  const w = x => `${Math.min(100, x / top * 100)}%`
  const pace = co.pace
  return <div className="plan">
    <div className="planhead"><b>{mln(co.net)}</b><span className="muted small">без НДС · {co.step ? `ступень ${co.step}, ${co.pct}%` : 'ступень ещё не взята'}</span></div>
    <div className="planbar">
      {pace && pace.net > co.net && <i className="pace" style={{ width: w(pace.net) }} />}
      <i className="fill" style={{ width: w(co.net) }} />
      {steps.map((s, i) => <span key={i} className={'tick' + (co.net > s.from ? ' got' : '')} style={{ left: w(s.from) }}><em>{mln(s.from)}</em><em>{s.pct}%</em></span>)}
    </div>
    {co.next ? <p className="small">До ступени {co.next.step} ({steps[co.next.step - 1]?.pct}%) — ещё <b>{money(co.next.left)}</b> без НДС.</p>
      : <p className="small">Верхняя ступень взята{m.bonus_plan ? `, бонус за план ${money(m.bonus_plan)}` : ''}.</p>}
    {pace && pace.day < pace.days && <p className="small muted">По темпу ({pace.day} из {pace.days} дней) к концу месяца ≈ {mln(pace.net)} → {pace.step ? `ступень ${pace.step}, ${pace.pct}%` : 'без ступени'}, заработок ≈ {money(pace.earn)}.</p>}
  </div>
}

export function Month({ openDeal }) {
  const now = new Date()
  const [ym, setYm] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const [m, setM] = useState(null)
  const [err, setErr] = useState('')
  useEffect(() => { setM(null); api(`/bx/month?ym=${ym}`).then(setM, e => setErr(e.message)) }, [ym])
  const cur = ym >= `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const nav = <div className="seg"><button className="ghost" disabled={ym <= '2026-11'} onClick={() => setYm(ymShift(ym, -1))}>←</button><button className="ghost" disabled>{ymName(ym)}</button><button className="ghost" disabled={cur} onClick={() => setYm(ymShift(ym, 1))}>→</button></div>
  if (err) return <div className="card"><h2>Мой месяц</h2>{nav}<p className="muted">{err}</p></div>
  if (!m) return <div className="card"><h2>Мой месяц</h2>{nav}<p className="muted">Считаю…</p></div>
  const co = m.company
  const deals = (ds, showMgr) => ds.map(d => <div key={d.id} className="row" onClick={() => openDeal(d.id)}><div><b>№ {d.id}</b> {d.title.replace(new RegExp(`^№?\\s*${d.id}\\s*·?\\s*`), '')}<div className="muted small">{[d.closed.split('-').reverse().join('.'), d.city, showMgr && d.manager].filter(Boolean).join(' · ')}</div></div><b>{money(d.sum)}</b></div>)
  return <>
    <div className="card dark"><h2>{m.all ? 'Месяц команды' : 'Мой месяц'}</h2>{nav}
      <Plan m={m} />
      <div className="kv">
        <div><span className="muted small">{cur ? 'Заработок сейчас' : 'Заработок за месяц'}</span><b>{money(co.earn)}</b></div>
        {m.all ? <div><span className="muted small">С НДС{m.vat ? ` ${m.vat}%` : ''}</span><b>{money(co.gross)}</b></div>
          : <div><span className="muted small">Мой вклад</span><b>{money(m.mine.net)}{m.mine.share ? <span className="muted small"> · {m.mine.share}%</span> : null}</b></div>}
      </div>
      {m.warn && <p className="small" style={{ color: 'var(--hot)' }}>{m.warn}</p>}
      <details className="how"><summary className="small muted">Как считается</summary>
        {!!m.salary && <p className="small muted">Заработок = оклад {money(m.salary)} + {co.pct || 0}% от выручки компании{co.plan_bonus ? ` + бонус за план ${money(co.plan_bonus)}` : ''}. Ступень считается по всей выручке компании за месяц без НДС. Выплаты отмечает HEAD.</p>}
        <p className="small muted">{m.source === 'sheet' ? 'Выручка — по листу «Проекты» финансовой таблицы (дата завершения работ, с НДС).' : 'Выручка — по дате закрытия сделок в Битриксе (пока в листе «Проекты» нет строк за этот месяц).'}</p>
      </details>
    </div>
    {cur && <SalesSpend won={co.count} />}
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

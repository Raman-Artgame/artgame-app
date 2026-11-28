import React, { useEffect, useRef, useState } from 'react'
import { api, uuid } from './api.js'
import { enqueue } from './queue.js'
import { SalesSpend } from './salesexp.jsx'
import { Tools } from './places.jsx'
import { CityPicker, Copy, Receipt, Sheet, WaitSheet, cityBase, useWide } from './ui.jsx'
import { shrink } from './work.jsx'
import { CallOutcome, Contact, Feed, Skeleton, bxLink, cleanTitle, dt, money, strip, usePortal } from './crm.jsx'
import { leftText } from './projects.jsx'
import { FillBar, FillSheet, LOCK_DOCS, LOCK_KP, Locked, anketaKey, lockFor, missingFor } from './fill.jsx'
import { ClosePanel, READY } from './closing.jsx'
import { ClientSheet, SignedUpload } from './mopforms.jsx'
import { DealDesign } from './designtasks.jsx'
import { DealPath, ProductionSheet } from './relay.jsx'

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
const STEPS = [['client', 'Клиент'], ['calc', 'Расчёт'], ['kp', 'КП'], ['docs', 'Договор'], ['pay', 'Оплата'], ['work', 'В работе'], ['close', 'Закрытие']]
// скрипты рабочего места по шагам алгоритма (rm_extra.js STEP_SCR) → панели карточки
const STEP_SCR = { '01': ['С1', 'С2', 'С3', 'Ж1', 'Ж2'], '03': ['С4', 'С5', 'С8', 'Ж3', 'Ж4', 'Ж5'], '05': ['С6', 'С7', 'Д1', 'Д2', 'Д3'], '06': ['С8', 'С26', 'С13', 'Ж16'],
  '07': ['Д4', 'Д5', 'Д6', 'Д7'], '08': ['Д7', 'Д8'], '09': ['С17', 'С23', 'С24', 'Ж17', 'Ж18'], '12': ['С25'] }
const PANEL_ALGO = { client: ['01', '03'], calc: ['05'], kp: ['06'], docs: ['09', '07'], pay: ['09'], work: ['12'], close: ['12'], hist: ['12'] }
const tomorrow = () => new Date(Date.now() + 86400000).toISOString().slice(0, 10)
const autoDesign = m2 => m2 < 30 ? 'S' : m2 < 200 ? 'M' : m2 < 1000 ? 'L' : 'XL'
const MAT = [['ARTGAME_Price_2026_phone.pdf', 'Прайс 2026', 'для WhatsApp'], ['ARTGAME_Price_paintings_2026_phone.pdf', 'Прайс картин', 'для WhatsApp'],
  ['ARTGAME_Catalog_FixPrice_2026_phone.pdf', 'Каталог фикс-прайса', 'рисунки 01–32'], ['ARTGAME_Object_requirements_phone.pdf', 'Подготовка объекта', 'стены, доступ, условия'],
  ['ARTGAME_Warranty_care_phone.pdf', 'Гарантия и уход', 'срок, что покрывает'], ['ARTGAME_Company_card.pdf', 'Карточка компании', 'наши реквизиты']]

function steps(d, calc) {
  const has = t => d.files.some(f => f.title.startsWith(t))
  return [['client', !!(d.client?.phone || d.client?.name)], ['calc', !!(calc?.out?.total) || !!d.norm.shifts], ['kp', KP_ON.has(d.stage) || has('КП')],
    ['docs', DOG_ON.has(d.stage) || has('Договор')], ['pay', d.pay.received > 0], ['work', WORK_ON.has(d.stage)], ['close', d.stage === 'WON']]
}

let scriptsCache = null
function useScripts() {
  const [s, setS] = useState(scriptsCache)
  useEffect(() => { if (!scriptsCache) api('/bx/scripts').then(r => { scriptsCache = r; setS(r) }, () => setS({ scr: { p1: [], p2: [] }, algo: { steps: [] } })) }, [])
  return s
}
const allScr = s => [...(s?.scr?.p1 || []), ...(s?.scr?.p2 || [])].flatMap(([, items]) => items)

// «Ответить клиенту» (HEAD 26.11): в реплики подставляются данные сделки — имя клиента, имя МОП, площадь, сумма, срок, объект.
// Чего в сделке нет, остаётся в [скобках] и подсвечено — МОП дописывает сам. Суммы — из согласованного КП, иначе из расчёта, иначе ориентир.
const num = n => n ? Math.round(n).toLocaleString('ru-RU') : ''
const first = s => (s || '').replace(/^(ТОО|ИП|АО)\s*«[^»]*»\s*·?\s*/, '').trim().split(/\s+/)[0] || ''
export function scriptCtx(d, calc) {
  const c = d.client || {}
  const r = calc?.out, area = +calc?.in?.area || d.area || 0
  const total = d.kp_agreed?.total || r?.total || d.sum || 0
  const days = r?.norm?.client || d.norm?.term
  const obj = d.object || cleanTitle(d.title, d.id)
  const name = first(c.type === 'Физлицо' || !d.contact ? c.name : d.contact)
  const v = { name, me: first(d.manager), area: area ? num(area) : '', size: area ? num(area) + ' м²' : '', sum: num(total), dsum: num(r?.dprice),
    days: days ? days + ' раб. дн.' : '', daysKz: days ? days + ' жұмыс күні' : '', obj, objCity: [obj, d.city].filter(Boolean).join(', ') }
  return {
    '[Имя]': v.name, '[Есімі]': v.name, '[Ваше имя]': v.me, '[Атыңыз]': v.me,
    '[площадь]': v.area, '[аудан]': v.area, '[размер]': v.size, '[өлшем]': v.size,
    '[сумма]': v.sum, '[сома]': v.sum, '[дни]': v.days, '[күндер]': v.daysKz,
    '[объект]': v.obj, '[нысан]': v.obj, '[объект, город]': v.objCity, '[нысан, қала]': v.objCity,
    _design: v.dsum,   // Д4/Д5: [сумма] — цена дизайна, не проекта
  }
}
const DESIGN_SUM = new Set(['Д4', 'Д5'])
function fillScript(t, ctx, code) {
  const map = DESIGN_SUM.has(code) ? { ...ctx, '[сумма]': ctx._design, '[сома]': ctx._design } : ctx
  const parts = (t || '').split(/(\[[^\]]{1,60}\])/)
  const out = parts.map(x => /^\[.*\]$/.test(x) && map[x] ? { t: map[x], ok: true } : { t: x, gap: /^\[.*\]$/.test(x) })
  return { text: out.map(x => x.t).join(''), parts: out, gaps: out.filter(x => x.gap).length }
}

// Скрипты шага во всплывающем окне: русский / казахский, каждая реплика копируется одной кнопкой; данные сделки уже подставлены.
function Scripts({ codes, title, onClose, algoStep, ctx, link }) {
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
    {ctx && <p className="small muted">Имя, сумма, площадь и срок уже из сделки. <mark className="gap">[В скобках]</mark> — допишите сами. Отправляйте клиенту через Битрикс.</p>}
    {link && <div className="dealbtns"><a className="btn mini" href={link} target="_blank" rel="noreferrer">Открыть переписку в Битриксе</a></div>}
    {s && !list.length && <p className="muted">Для этого шага готовых реплик нет — см. учебник во вкладке «Учёба».</p>}
    {list.map(x => { const t = lang === 'kz' && x.kz ? x.kz : x.ru
      const f = ctx ? fillScript(t, ctx, x.c) : { text: t, parts: [{ t }], gaps: 0 }
      return <div key={x.c} className="scr"><div><span className="code">{x.c}</span><b>{x.s}</b></div>
        <div className="st">{f.parts.map((p, i) => p.ok ? <b key={i} className="fill">{p.t}</b> : p.gap ? <mark key={i} className="gap">{p.t}</mark> : <React.Fragment key={i}>{p.t}</React.Fragment>)}</div>
        {x.n && <div className="sn">{x.n}</div>}<div className="dealbtns"><Copy text={f.text} />{f.gaps > 0 && <span className="small muted">дописать: {f.gaps}</span>}{lang === 'kz' && !x.kz && <span className="small muted">только на русском</span>}</div></div> })}
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
    <select value={stage} onChange={e => setStage(e.target.value)}>{stages.filter(s => s.id !== 'WON' || s.id === d.stage).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
    {d.stage === READY && <p className="small muted">«Оплата получена» — через шаг «Закрытие»: «На закрытие», дальше решает HEAD.</p>}
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
// Командировка (HEAD 08.11): по умолчанию — сама по городу сотрудника и объекта; МОП может поправить. Только в приложении.
function Trip({ id }) {
  const [t, setT] = useState(undefined)
  const [msg, setMsg] = useState('')
  useEffect(() => { api(`/objects/${id}/trip`).then(o => setT(o.trip), () => setT('none')) }, [id])
  if (t === undefined) return null
  if (t === 'none') return <p className="small muted">Командировка: объект появится в приложении со стадии «Отправка счёта», тогда можно отметить.</p>
  const put = v => api(`/objects/${id}/trip`, { method: 'POST', body: { trip: v } }).then(o => { setT(o.trip); setMsg('') }, e => setMsg(e.message))
  return <><label>Командировка <span className="muted">· суточные и дорога команде считаются сами</span></label>
    <div className="chips">{[[null, 'По городу'], [true, 'Да, выезд'], [false, 'Нет, в городе']].map(([v, n]) => <button key={String(v)} className={t === v ? 'on' : ''} onClick={() => put(v)}>{n}</button>)}</div>
    {msg && <p className="small why">{msg}</p>}</>
}

// «Клиент согласовал КП» (схема HEAD 26.11): сумма и нормы закрепляются; поменять — только «Снять согласование» с причиной.
function KpAgree({ d, onDone }) {
  const [undo, setUndo] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const a = d.kp_agreed
  const hasKp = (d.files || []).some(f => (f.title || '').startsWith('КП'))
  const go = (path, body, t) => { setBusy(true); setErr(''); api(`/bx/deals/${d.id}/${path}`, { method: 'POST', body }).then(() => onDone(t), e => setErr(e.message)).finally(() => setBusy(false)) }
  if (a) return <div className="kpagree on">
    <div><b>Клиент согласовал КП</b><span className="small muted">{money(a.total)} · {dt(a.at)} · {a.by}. Сумма и нормы закреплены.</span></div>
    {undo === null ? <button className="ghost mini" onClick={() => setUndo('')}>Снять согласование</button>
      : <><input value={undo} onChange={e => setUndo(e.target.value)} placeholder="Почему: клиент попросил другую площадь…" />
        <div className="dealbtns wrapbtns"><button className="mini" disabled={busy || undo.trim().length < 3} onClick={() => go('kp-agreed/undo', { reason: undo.trim() }, 'Согласование снято — можно пересчитать.')}>Снять</button>
          <button className="ghost mini" onClick={() => setUndo(null)}>Отмена</button></div></>}
    {err && <p className="small why">{err}</p>}
  </div>
  if (!hasKp || !d.sum) return <p className="small muted">Когда КП скачано и клиент согласился — здесь появится кнопка «Клиент согласовал КП».</p>
  return <div className="kpagree">
    <button disabled={busy} onClick={() => go('kp-agreed', {}, 'Клиент согласовал КП: сумма и нормы закреплены.')}>Клиент согласовал КП</button>
    <span className="small muted">Сумма {money(d.sum)} и нормы закрепятся; договор и счёт возьмут их.</span>
    {err && <p className="small why">{err}</p>}
  </div>
}

// Расчёт (HEAD 26.11 «у нас есть полноценный блок — какого он в учебнике»): в шаге — тот же калькулятор, что в блоке
// «Расчёт · КП · Документы · Скрипты», данные сделки подставлены. «Записать в сделку» под итогом → сервер пересчитывает
// по «Значениям» и пишет сумму, площадь, нормы в Битрикс; ниже — что записано и что увидит команда.
const TAB_SVC = { paint: 'mural', print: 'print', fix: 'fix', bulk: 'bulk' }
const SVC_TAB = { mural: 'paint', print: 'print', fix: 'fix', bulk: 'bulk' }
const byVal = (m, v) => Object.keys(m).find(k => m[k] === v)
function calcState(d, saved) {
  const i = saved?.in || {}, svc = i.service || (/печат/i.test(d.service || '') ? 'print' : 'mural'), m2 = +(i.area || d.area || 0)
  const ex = i.extras || [], st = { tab: SVC_TAB[svc] || 'paint', place: i.place || 'base', cash: +i.cash || 0,
    ex: { urgent: ex.includes('urgent'), height: ex.includes('height'), night: ex.includes('night'), lac: ex.includes('lacquer') },
    dx: { urgent: !!i.design_urgent, concept: !!i.design_concept, extra: +i.design_extra || 0 } }
  const design = i.design || (m2 ? autoDesign(m2) : undefined)
  if (m2) { st.paint = { m2, level: LEVELS[svc === 'mural' && i.level ? i.level : d.level || 'medium'] || 'Средний', ...(design ? { design } : {}) }
    st.print = { m2, ...(design ? { design } : {}) }; st.bulk = { m2 } }
  if (svc === 'fix') st.fix = { level: FIX[i.level] || 'Лёгкий', qty: +i.qty || 1 }
  return st
}
function priceIn(S, team) {
  const t = S.tab, area = +((t === 'paint' ? S.paint : t === 'print' ? S.print : t === 'bulk' ? S.bulk : null)?.m2 || 0)
  return { service: TAB_SVC[t], area, level: t === 'fix' ? byVal(FIX, S.fix?.level) || 'lite' : byVal(LEVELS, S.paint?.level) || 'medium',
    design: t === 'paint' ? S.paint?.design || null : t === 'print' ? S.print?.design || null : null,
    extras: ['urgent', 'height', 'night'].filter(k => S.ex?.[k]).concat(S.ex?.lac ? ['lacquer'] : []),
    place: S.place || 'base', cash: +S.cash || 0, qty: +S.fix?.qty || 1, design_urgent: !!S.dx?.urgent, design_concept: !!S.dx?.concept,
    design_extra: +S.dx?.extra || 0, outdoor: team.outdoor, surface: team.surface }
}
// Шаг «Расчёт» в карточке — только итог; сам расчёт — в блоке «Расчёт и КП» окном поверх сделки (HEAD 26.11, вариант «окно из сделки»)
function CalcSum({ d, saved, open }) {
  const r = saved?.out, n = r?.norm || {}
  return <div className="card calcsum">
    <div className="panelhead"><h3>Расчёт</h3><span className="small muted">{saved ? `записан ${dt(saved.at)}` : 'ещё не считали'}</span></div>
    {d.kp_agreed && <p className="small why">КП согласовано клиентом на {money(d.kp_agreed.total)} — сумма и нормы закреплены. Новую цену — после «Снять согласование» в шаге «КП».</p>}
    {r ? <div className="kv">
      <div><span className="muted small">{r.no_vat ? 'Итого по акции, без НДС' : 'Итого с НДС'}</span><b>{money(r.total)}</b></div>
      <div><span className="muted small">Аванс {r.pay.prepay_pct}%</span><b>{money(r.pay.prepay)}</b></div>
      {r.dprice ? <div><span className="muted small">Дизайн {r.design}, 100% вперёд</span><b>{money(r.dprice)}</b></div> : null}
      {n.shifts ? <><div><span className="muted small">Смен по норме</span><b>{n.shifts}</b></div>
        <div><span className="muted small">Художников</span><b>{n.crew}</b></div>
        <div><span className="muted small">Срок клиенту</span><b>{n.client} раб. дн.</b></div></> : null}
    </div> : <p className="small muted">Посчитайте в блоке «Расчёт и КП»: услуга и площадь сделки там уже стоят. «Записать в сделку» под итогом — и сумма, аванс, смены и срок появятся здесь.</p>}
    <div className="dealbtns wrapbtns">
      <button onClick={() => open('calc')}>{r ? 'Пересчитать в «Расчёт и КП»' : 'Открыть «Расчёт и КП»'}</button>
      {r && <Copy text={r.client_text} label="Скопировать текст клиенту" />}
    </div>
    <Trip id={d.id} />
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

function WorkPanel({ d, portal, onProd }) {
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
    {(d.pay.received > 0 || d.pay.on_check > 0 || WORK_ON.has(d.stage)) &&
      <button className={'mini' + (WORK_ON.has(d.stage) ? ' ghost' : '')} onClick={onProd}>{WORK_ON.has(d.stage) ? 'ГИП и сроки' : 'В производство'}</button>}
    <p className="small muted">ГИП получает сообщение сам и ставит людей на объект. Дата старта называется клиенту только после подтверждения загрузки (скрипт С23).</p>
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

// Оплаты сделки (HEAD 10.11): журнал приложения — внесённые здесь, из полей «Поступление» и HEAD; ниже — история из полей сделки
// год — только у прошлогодних оплат: «10 нояб.», но «5 дек. 2025»
const pdate = x => { if (!x) return 'без даты'; const t = new Date(x); return t.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', ...(t.getFullYear() !== new Date().getFullYear() && { year: 'numeric' }) }) }
// slot — оплата из поля «Поступление N» сделки без даты (так вносили до 10.11): «Дата и чек» заменяет её оплатой с датой и чеком
export function Payments({ pay, onDate }) {
  const rows = [...(pay.items || []), ...(pay.history || []).map(h => ({ ...h, hist: true, op_date: h.date }))]
  if (!rows.length) return <p className="small muted">Оплат по сделке ещё нет.</p>
  return <div className="paylist">{rows.map((x, i) => <div key={x.id || 'h' + i} className="row" style={x.status === 'cancelled' ? { opacity: .45, textDecoration: 'line-through' } : null}>
    <div><b>{money(x.amount)}</b> <span className="small muted">{x.hist ? 'из поля сделки' : x.account_title}</span>
      <div className="small muted">{[x.slot ? 'без даты' : pdate(x.op_date), !x.hist && (x.source === 'bitrix' ? 'из поля «Поступление»' : x.author), x.status === 'cancelled' && 'отменено HEAD'].filter(Boolean).join(' · ')}
        {x.receipt_url ? <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></> : x.source === 'app' && ' · без чека'}</div></div>
    {x.on_check && <span className="tag draft">на сверке</span>}
    {x.slot && onDate && <button className="mini" onClick={() => onDate(x)}>Дата и чек</button>}
  </div>)}</div>
}

// «Внести оплату»: сумма, дата (сегодня), счёт, фото чека (наличными — по желанию). Нет сети — запись ждёт на телефоне и уходит сама.
// Оплата до 01.11.2026 (нашли задним числом) — в счёт «История»: долг сделки уменьшает, в деньги ноября не входит.
const START = '2026-11-01'
// slot — «Дата и чек» к оплате из поля «Поступление N» без даты: сумма уже стоит, оплата заменит поле, двойного счёта нет.
export function PaySheet({ d, slot, onClose, onDone }) {
  const today = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Almaty' })
  const accounts = d.pay.accounts || []
  // счёт выбирают сами, без подстановки (HEAD 11.11: два ИП — Яковлев и Артамонов, ошибка в счёте = ошибка в налогах)
  const [v, set] = useState({ amount: slot ? String(Math.round(slot.amount)) : '', op_date: today, account: '', note: '', receipt: '', cash: false })
  const fits = (a, day) => !a.valid_until || day <= a.valid_until   // «ИП Артамонов» — только оплаты по 31.12.2026
  const accs = accounts.filter(a => fits(a, v.op_date))
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const hist = !!v.op_date && v.op_date < START
  const cash = hist ? v.cash : v.account === 'cash'   // наличными — фото расписки по желанию (HEAD 10.11)
  const undated = slot ? [] : [...(d.pay.items || []), ...(d.pay.history || [])].filter(x => x.slot)
  const send = async () => {
    const path = `/bx/deals/${d.id}/payment`
    const body = { client_uid: uuid(), amount: +v.amount, op_date: v.op_date, account: hist ? 'hist' : v.account, note: v.note.trim() || null, receipt: v.receipt || null,
      ...(slot && { slot: slot.slot }), ...(hist && cash && { cash: true }) }
    setBusy(true); setErr('')
    try {
      await api(path, { method: 'POST', body })
      onDone(slot ? 'Дата и чек сохранены: оплата заменила поле сделки, HEAD сверит.' : d.pay.count_unchecked ? 'Оплата внесена: «Поступило» обновлено, HEAD сверит чек.' : 'Оплата внесена: войдёт в «Поступило» после сверки HEAD.')
    } catch (e) {
      if (!e.status || e.status >= 500) { await enqueue(path, body); onDone('Нет связи с сервером: оплата сохранена на телефоне и уйдёт сама.') }
      else setErr(e.message)
    } finally { setBusy(false) }
  }
  return <Sheet title={slot ? 'Дата и чек к оплате' : 'Внести оплату'} onClose={onClose}>
    <div className="dealedit">
      {slot && <p className="small muted">Оплата {money(slot.amount)} из поля «Поступление {slot.slot}» без даты. Укажите дату и фото чека: она заменит поле, двойного счёта не будет.</p>}
      {!!undated.length && <p className="small why">В сделке есть оплата без даты: {undated.map(x => money(x.amount)).join(', ')}. Если вносите её, закройте это окно и нажмите «Дата и чек» у неё в списке, иначе она задвоится.</p>}
      <input inputMode="numeric" value={v.amount} onChange={e => set({ ...v, amount: e.target.value.replace(/\D/g, '') })} placeholder="Сумма, ₸" />
      <label className="small muted">Дата оплаты <input type="date" value={v.op_date} min="2025-01-01" max={today} onChange={e => { const day = e.target.value; set({ ...v, op_date: day, account: accounts.some(a => a.code === v.account && fits(a, day)) ? v.account : '' }) }} /></label>
      {hist ? <>
        <p className="small why">Оплата до ноября уйдёт в «Историю»: долг сделки уменьшит, в деньги ноября не войдёт.</p>
        <div className="chips"><button className={v.cash ? 'on' : ''} onClick={() => set({ ...v, cash: !v.cash })}>Наличные</button></div>
      </> : <>
        <div className="chips">{accs.map(a => <button key={a.code} className={v.account === a.code ? 'on' : ''} onClick={() => set({ ...v, account: a.code })}>{a.title}</button>)}</div>
        {!v.account && <p className="small muted">Выберите счёт, куда пришли деньги.</p>}
      </>}
      <input value={v.note} onChange={e => set({ ...v, note: e.target.value })} placeholder="Комментарий, например «аванс 50%»" />
      <Receipt value={v.receipt} need={!cash} pick={async f => set({ ...v, receipt: await shrink(f) })} />
      {cash && !v.receipt && <p className="small muted">Наличные: добавьте фото расписки, если она есть. Без фото HEAD сверит сам.</p>}
      {err && <p className="small why">{err}</p>}
      <div className="dealbtns"><button disabled={busy || !(+v.amount > 0) || !(v.receipt || cash) || !v.op_date || !(hist || v.account)} onClick={send}>{busy ? 'Отправляю…' : `${slot ? 'Сохранить' : 'Внести'} ${+v.amount > 0 ? money(+v.amount) : ''}`}</button>
        <button className="ghost" onClick={onClose}>Отмена</button></div>
    </div>
  </Sheet>
}

// Боковой блок сделки на компьютере (HEAD 26.11): основные показатели одним столбиком и подсказки. Показатели шапки (сумма, площадь,
// услуга, город) на компьютере живут только здесь — в шапке они скрыты, чтобы не повторяться. Подсказки: сейчас — по данным сделки;
// d.hints — место под подсказки ботов-аналитиков переписки и звонков ([{text, at, from}] в /bx/deals/{id}/full, пока сервер их не отдаёт).
const DAY = 86400000
const daysAgo = at => at ? Math.max(0, Math.floor((Date.now() - new Date(at).getTime()) / DAY)) : null
const daysTxt = n => n === null ? '—' : n === 0 ? 'сегодня' : n + ' ' + (n % 10 === 1 && n % 100 !== 11 ? 'день' : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? 'дня' : 'дней')
function sideHints(d, calc, inStage, touch) {
  const out = [], early = !WORK_ON.has(d.stage) && d.stage !== 'LOSE'
  if (early && !calc && !d.kp_agreed) out.push('Нет расчёта — посчитайте в «Расчёт и КП», чтобы назвать клиенту цену и срок.')
  if (early && touch !== null && touch >= 3) out.push(`Клиент без касания ${daysTxt(touch)} — позвоните или напишите, договоритесь о следующем шаге.`)
  if (early && inStage !== null && inStage >= 7) out.push(`Сделка ${daysTxt(inStage)} на стадии «${d.stage_name}» — уточните, что мешает двигаться дальше.`)
  if (d.pay.debt > 0 && (d.pay.received > 0 || WORK_ON.has(d.stage))) out.push(`Долг ${money(d.pay.debt)} — напомните об оплате, скрипт в шаге «Оплата».`)
  if (calc && !d.kp_agreed && KP_ON.has(d.stage)) out.push('Когда клиент согласится с КП — нажмите «Клиент согласовал КП», сумма закрепится.')
  return out
}
function DealSide({ d, calc }) {
  const sold = d.kp_agreed ? '✓' : calc ? '' : '≈'
  const inStage = daysAgo(d.history?.[0]?.at)
  const touch = daysAgo(d.feed?.[0]?.at)
  const term = calc?.out?.norm?.client || d.norm?.term
  const rules = sideHints(d, calc, inStage, touch)
  const bots = Array.isArray(d.hints) ? d.hints : []
  const row = (k, v, cls = 'n') => <div className={'srow' + (cls ? ' ' + cls : '')}><span className="muted small">{k}</span><b>{v}</b></div>
  return <aside className="dealside">
    <div className="card">
      <h3>Показатели</h3>
      {row('Сумма', <>{sold && <em title={sold === '✓' ? 'согласовано клиентом' : 'ориентир'}>{sold}</em>} {money(d.sum)}</>)}
      {row('Поступило', money(d.pay.received))}
      {row(d.pay.lost ? 'Упущено' : 'Долг', money(d.pay.lost || d.pay.debt), (d.pay.debt > 0 && d.pay.received > 0) ? 'n warn' : 'n')}
      {calc && row('Аванс по расчёту', money(calc.out.pay.prepay))}
      {row('Площадь', d.area ? d.area + ' м²' : '—')}
      {row('Услуга', d.service || '—', ' ')}
      {row('Город', d.city || '—')}
      {row('Срок работ', term ? term + ' раб. дн.' : '—')}
      {row('На стадии', daysTxt(inStage))}
      {row('Последнее касание', touch === null ? '—' : touch === 0 ? 'сегодня' : daysTxt(touch) + ' назад', touch >= 3 && !WORK_ON.has(d.stage) ? 'n warn' : 'n')}
    </div>
    <div className="card hints">
      <h3>Подсказки</h3>
      {rules.map((t, i) => <p key={i} className="small">{t}</p>)}
      {!rules.length && !bots.length && <p className="small muted">По данным сделки всё в порядке.</p>}
      {bots.map((h, i) => <p key={'b' + i} className="small bot">{h.text}{(h.reason || h.at) && <span className="muted"><br />{[h.reason, h.at && 'клиент писал ' + new Date(h.at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })].filter(Boolean).join(' · ')}</span>}</p>)}
      {!bots.length && <div className="botslot small muted">Здесь будут подсказки по переписке и звонкам: что клиент спросил, что мы обещали, риск отказа. Их пришлют боты-аналитики — по утрам.</div>}
    </div>
  </aside>
}

export function DealCard({ id, back, place }) {
  const [d, setD] = useState(null)
  const [err, setErr] = useState('')
  const [stages, setStages] = useState([])
  const [calc, setCalc] = useState(undefined)
  const [panel, setPanel] = useState(null)
  const [moreActs, setMoreActs] = useState(false)
  const [sheet, setSheet] = useState(null)   // {kind: call|stage|note|say, ...}
  const [tools, setTools] = useState(null)   // блок «Расчёт и КП» окном: 'calc' | 'kp' | 'docs'
  const [team, setTeam] = useState(null)     // для нормы смен: улица, сложная поверхность
  const [msg, setMsg] = useState('')
  const portal = usePortal()
  const wide = useWide()
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
  const NEXT = { client: 'Заполнить и позвонить', calc: 'Посчитать цену и срок', kp: 'Собрать КП', docs: 'Договор и счёт', pay: 'Оплата', work: 'Проект',
    close: d.stage === READY ? 'На закрытие' : 'Что нужно' }
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
  const tm = team || { outdoor: !!calc?.in?.outdoor, surface: !!calc?.in?.surface }
  const onCalc = (m, reply) => {   // «Записать в сделку» из блока: сервер пересчитывает по «Значениям» и пишет в Битрикс
    if (d.kp_agreed) return reply(false, `КП согласовано клиентом на ${money(d.kp_agreed.total)}. Новую цену — после «Снять согласование» в шаге «КП».`)
    if (!TAB_SVC[m.state.tab]) return reply(false, 'Картины пока считаются здесь только для клиента: в сделку их запишем после обновления калькулятора картин.')
    api(`/bx/deals/${d.id}/price/save`, { method: 'POST', body: priceIn(m.state, tm) }).then(x => {
      const got = x.calc?.total || 0, diff = Math.round(got) !== Math.round(m.total)
      const text = (x.bx === 'off' ? 'Расчёт сохранён, в Битрикс не записан (ключ записи не задан).' : `Записано в сделку: ${money(got)}, площадь, смены и срок.`)
        + (diff ? ` Внимание: блок показал ${money(m.total)}, по «Значениям» на сервере — ${money(got)}; записано ${money(got)}. Скажите HEAD.` : '')
      reply(true, text); loadCalc(); load(true); setMsg(text); setTimeout(() => setMsg(''), 8000)
    }, e => reply(false, 'Не записалось: ' + e.message))
  }
  return <>
    <div className="hero">
      <a className="back" onClick={back}>← к сделкам</a>
      <h2>№ {d.id} · {cleanTitle(d.title, d.id)} <button className="pencil" aria-label="Изменить название" onClick={() => setSheet({ kind: 'title' })}>✎</button></h2>
      <span className="tag">{d.stage_name}</span>{d.manager && <span className="tag">{d.manager}</span>}
      <DealPath dealId={d.id} stage={d.stage} reload={d} />
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
        : <div><b>Все шаги пройдены</b><span className="small muted">{d.stage === 'WON' ? 'сделка закрыта · оплата получена' : 'проект в работе'}</span></div>}</div>
      {/* HEAD 14.11 «максимально удобно и понятно»: на виду — три частых действия, редкие — под «Ещё действия» */}
      <div className="dealbtns wrapbtns">
        <button className="ghost" onClick={() => setSheet({ kind: 'call' })}>Итог звонка</button>
        <button className="ghost" onClick={() => setSheet({ kind: 'wait' })}>Жду ответа</button>
        <button className="ghost" onClick={say}>Ответить клиенту</button>
        <button className={'ghost morebtn' + (moreActs ? ' on' : '')} aria-expanded={moreActs} onClick={() => setMoreActs(!moreActs)}>Ещё действия {moreActs ? '▴' : '▾'}</button>
      </div>
      {moreActs && <div className="dealbtns wrapbtns moreacts">
        <button className="ghost" onClick={() => setSheet({ kind: 'fill' })}>Заполнить карточку</button>
        <button className="ghost" onClick={() => setSheet({ kind: 'client' })}>Клиент и реквизиты</button>
        <button className="ghost" onClick={() => setSheet({ kind: 'note' })}>Заметка</button>
        <button className="ghost" onClick={() => setSheet({ kind: 'stage' })}>Стадия</button>
        <button className={'ghost' + (cur === 'hist' ? ' on' : '')} onClick={() => setPanel('hist')}>История</button>
      </div>}
    </div>
    {wide && <DealSide d={d} calc={calc} />}
    {msg && <div className="toast">{msg}</div>}
    {tools && <Tools place={place} dealId={d.id} title={`№ ${d.id} · ${cleanTitle(d.title, d.id)}`} view={tools} calc={calcState(d, calc)} kp={kpItem} ds={ds}
      onDoc={onDoc} onCalc={onCalc} close={() => { setTools(null); load(true); loadCalc() }}
      bar={<div className="calcteam"><span className="small muted">Для нормы смен:</span>
        <button className={'mini' + (tm.outdoor ? '' : ' ghost')} onClick={() => setTeam({ ...tm, outdoor: !tm.outdoor })}>Улица</button>
        <button className={'mini' + (tm.surface ? '' : ' ghost')} onClick={() => setTeam({ ...tm, surface: !tm.surface })}>Сложная поверхность</button></div>} />}
    <DealDesign dealId={d.id} />

    {cur === 'client' && <div className="card">
      <div className="panelhead"><h3>Клиент</h3><button className="ghost mini" onClick={say}>Скрипты шага</button></div>
      <div className="hint"><div><b>Шаг 1–3.</b> Ответить в течение 30 минут, узнать помещение, город, площадь и фото стены; назвать ориентир по лестнице цены; договориться о следующем касании.</div></div>
      <Qualify key={d.modified} d={d} onDone={() => load(true)} />
      <button className="ghost clientbtn" onClick={() => setSheet({ kind: 'client' })}>Клиент и реквизиты: {c.type || 'Физлицо'}{c.name ? ' · ' + c.name : ''}</button>
    </div>}
    {cur === 'calc' && <CalcSum d={d} saved={calc} open={setTools} />}
    {cur === 'kp' && <>
      <div className="card">
        <div className="panelhead"><h3>Коммерческое предложение</h3><button className="ghost mini" onClick={say}>Скрипты шага</button></div>
        {calc ? <p className="small muted">Позиция из расчёта ({money(calc.out.total)}) уже в КП, клиент и сделка подставлены. Проверьте, скачайте PDF — файл ляжет в сделку Битрикса, стадия сменится на «Отправка КП».</p>
          : <p className="small why">Сначала сделайте расчёт — тогда КП соберётся без ввода цифр. <a onClick={() => setPanel('calc')}>К расчёту</a></p>}
        {lockKP.length ? <Locked what="КП" miss={lockKP} onFill={fillIt} onCalc={() => setPanel('calc')} />
          : <div className="dealbtns wrapbtns"><button onClick={() => setTools('kp')}>Собрать КП в «Расчёт и КП»</button></div>}
        <KpAgree d={d} onDone={said} />
      </div>
      <Materials place={place} d={d} portal={portal} />
    </>}
    {cur === 'docs' && <>
      <div className="card">
        <div className="panelhead"><h3>Договор, счёт, акт</h3><button className="ghost mini" onClick={say}>Скрипты шага</button></div>
        <p className="small muted">{calc ? `Сумма ${money(calc.out.total)} и аванс ${money(calc.out.pay.prepay)} — из расчёта; ` : ''}клиент и реквизиты — из карточки клиента. Скачанный файл ложится в сделку, стадия — «Отправка счёта/договора».</p>
        <button className="ghost mini" onClick={() => setSheet({ kind: 'client' })}>{d.requisites?.cbin || c.type === 'Физлицо' ? 'Клиент и реквизиты' : 'Внести реквизиты клиента'}</button>
        {lockDocs.length ? <Locked what="Договор и счёт" miss={lockDocs} onFill={fillIt} onCalc={() => setPanel('calc')} />
          : <div className="dealbtns wrapbtns"><button onClick={() => setTools('docs')}>Договор, счёт, акт в «Расчёт и КП»</button></div>}
      </div>
      <SignedUpload d={d} onDone={(r, t) => said(t)} />
      {!!d.files.length && <div className="card"><h3>Документы в сделке</h3>
        {d.files.map((f, i) => <div key={i} className="row"><span>{f.title}</span>{f.url ? <a href={f.url} target="_blank" rel="noreferrer">открыть</a> : <span className="muted small">в Битриксе</span>}</div>)}</div>}
    </>}
    {cur === 'pay' && <>
      <div className="card"><h3>Оплата</h3>
        <div className="kv">
          <div><span className="muted small">Поступило</span><b>{money(d.pay.received)}</b></div>
          <div><span className="muted small">{d.pay.lost ? 'Упущено' : 'Долг'}</span><b>{money(d.pay.lost || d.pay.debt)}</b></div>
          {calc && <div><span className="muted small">Аванс по расчёту</span><b>{money(calc.out.pay.prepay)}</b></div>}
          {d.pay.next && <div><span className="muted small">Ближайший платёж</span><b>{d.pay.next.slice(0, 10)}</b></div>}
        </div>
        {d.pay.on_check > 0 && <p className="small why">На сверке у HEAD: {money(d.pay.on_check)}{d.pay.count_unchecked ? ' (уже в «Поступило»)' : ' (войдёт в «Поступило» после ✓ HEAD)'}.</p>}
        <Payments pay={d.pay} onDate={x => setSheet({ kind: 'pay', slot: x })} />
        <p className="small muted">Оплату вносите здесь, с фото чека: чек ляжет в папку сделки «Приходы чеки», HEAD сверит, «Поступило» и «Долг» в Битриксе приложение запишет само. Когда аванс пришёл и договор подписан — «В производство»: стадия, ГИП и сроки одной кнопкой.</p>
        <div className="dealbtns wrapbtns">
          <button className="mini" onClick={() => setSheet({ kind: 'pay' })}>+ Внести оплату</button>
          {/* «В производство» — только когда аванс уже пришёл (HEAD 14.11: без лишних кнопок раньше времени); эстафета HEAD 26.11:
              одна кнопка вместо «Перевести в работу» и «Передать куратору ГИП» */}
          {(d.pay.received > 0 || d.pay.on_check > 0) && !WORK_ON.has(d.stage) &&
            <button className="mini" onClick={() => setSheet({ kind: 'prod' })}>В производство</button>}
          <button className="ghost mini" onClick={say}>Скрипты шага</button>
        </div>
      </div>
      <SignedUpload d={d} onDone={(r, t) => said(t)} />
      <SalesSpend dealId={d.id} />
    </>}
    {cur === 'work' && <WorkPanel d={d} portal={portal} onProd={() => setSheet({ kind: 'prod' })} />}
    {cur === 'close' && <ClosePanel d={d} onDone={said} />}
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
    {sheet?.kind === 'client' && <ClientSheet dealId={d.id} onClose={() => setSheet(null)} onDone={said} />}
    {sheet?.kind === 'fill' && <FillSheet d={d} onClose={() => setSheet(null)} onDone={said}
      onClient={() => setSheet({ kind: 'client' })} onStep={k => { setSheet(null); setPanel(k) }} onProd={() => setSheet({ kind: 'prod' })}
      onDesign={() => { setSheet(null); setTimeout(() => document.querySelector('.dtdeal')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50) }} />}
    {sheet?.kind === 'prod' && <ProductionSheet dealId={d.id} onClose={() => setSheet(null)} onDone={said} onFill={() => setSheet({ kind: 'fill' })} />}
    {sheet?.kind === 'note' && <NoteSheet d={d} initial={sheet.text} onClose={() => setSheet(null)} onDone={said} />}
    {sheet?.kind === 'pay' && <PaySheet d={d} slot={sheet.slot} onClose={() => setSheet(null)} onDone={said} />}
    {sheet?.kind === 'say' && <Scripts codes={codes} algoStep={algo[0]} title={`Ответить клиенту: ${name(cur)}`} ctx={scriptCtx(d, calc)} link={portal ? bxLink(portal, 'deal', d.id) : ''} onClose={() => setSheet(null)} />}
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

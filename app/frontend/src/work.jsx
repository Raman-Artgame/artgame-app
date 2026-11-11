import React, { useEffect, useState } from 'react'
import { StatusMark, Receipt } from './ui.jsx'
import { api, testAs, uuid, viewAs } from './api.js'
import { clearFailed, enqueue, failed, flush, pending } from './queue.js'
import { startViewAs } from './head.jsx'
import { BOSS, HINT_TITLE, hintsFor } from './hints.js'

const ZONE = { mural: 'Роспись', print: 'Печать', design: 'Дизайн', sales: 'Продажи' }
const PRINT_ROLES = ['print_master', 'print_operator']
const ROLE_T = { support: 'Саппорт', artist: 'Художник', artist_pro: 'Художник Про', lead_artist: 'Главный художник',
  print_operator: 'Оператор печати', print_master: 'Мастер печати' }
const ST = { open: 'идёт', submitted: 'на проверке', approved: 'принято', rejected: 'отказ', cancelled: 'отменено' }
const local = d => { const x = new Date(d); x.setMinutes(x.getMinutes() - x.getTimezoneOffset()); return x.toISOString().slice(0, 16) }
const iso = v => new Date(v).toISOString()
const money = n => Number(n).toLocaleString('ru-RU') + ' ₸'

// Чек сжимаем на телефоне (до 1600 px, JPEG): быстрее уходит при плохой сети и помещается в офлайн-очередь.
export function shrink(file) {
  return new Promise((ok, fail) => {
    const img = new Image()
    img.onload = () => {
      const k = Math.min(1, 1600 / Math.max(img.width, img.height))
      const c = document.createElement('canvas'); c.width = img.width * k; c.height = img.height * k
      c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
      URL.revokeObjectURL(img.src); ok(c.toDataURL('image/jpeg', 0.75))
    }
    img.onerror = fail
    img.src = URL.createObjectURL(file)
  })
}

function useDict() {
  const [d, setD] = useState(null)
  useEffect(() => { api('/work/dict').then(d => { setD(d); localStorage.setItem('artgame.dict', JSON.stringify(d)) },
    () => setD(JSON.parse(localStorage.getItem('artgame.dict') || 'null'))) }, [])
  return d
}

function Common({ d, v, set }) {
  return <>
    <label className="muted">Объект</label>
    <select value={v.object_id} onChange={e => set({ ...v, object_id: +e.target.value })}>
      {d.objects.map(o => <option key={o.id} value={o.id}>{o.id ? `№${o.id} · ` : ''}{o.title}{o.city ? ` — ${o.city}` : ''}</option>)}
    </select>
    {d.zones.length > 1 && <>
      <label className="muted">Зона</label>
      <select value={v.zone_code} onChange={e => set({ ...v, zone_code: e.target.value })}>
        {d.zones.map(z => <option key={z} value={z}>{ZONE[z]}</option>)}
      </select></>}
  </>
}

const CX = [['easy', 'Лёгкий'], ['medium', 'Средний'], ['hard', 'Сложный'], ['author', 'Авторский']]
const pct = k => Math.round(k * 100) + '%'
// «7 нояб., 09:00–18:00» — без секунд, с концом смены
export const when = (a, b) => new Date(a).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) +
  (b ? '–' + new Date(b).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) +
    (new Date(b).toDateString() !== new Date(a).toDateString() ? ' след. дня' : '') + ` · ${Math.round((new Date(b) - new Date(a)) / 36e5 * 10) / 10} ч` : '')
const m2 = x => Number(x).toLocaleString('ru-RU', { maximumFractionDigits: 2 })


const LKEY = 'artgame.shift.open'
const loadOpen = () => { try { return JSON.parse(localStorage.getItem(LKEY) || 'null') } catch { return null } }
const saveOpen = v => { try { v ? localStorage.setItem(LKEY, JSON.stringify(v)) : localStorage.removeItem(LKEY) } catch { /* без памяти */ } }
const hm = ms => { const m = Math.max(0, Math.floor(ms / 60000)); return `${Math.floor(m / 60)} ч ${String(m % 60).padStart(2, '0')} мин` }
const LV = Object.fromEntries(CX)

// Живая карточка объекта (HEAD 08.11): что предстоит — условия из сделки (без выбора), сложность по сумме, если МОП не указал,
// эскизы с Диска (утверждённые первыми), карта, ход работ по сменам, этапы, фото «до / после». Тап по картинке — на весь экран.
const SRC = { calc: 'из расчёта МОП', price: 'оценка по сумме сделки' }
export function Promo({ id, zone, compact, onData, role }) {
  const [c, setC] = useState(null)
  const [big, setBig] = useState(null)
  const [ba, setBa] = useState(50)
  useEffect(() => { if (id) api(`/work/object/${id}?zone=${zone || 'mural'}`).then(x => { setC(x); onData?.(x) }, () => setC(null)) }, [id, zone])
  if (!id || !c) return null
  const conds = [['at_height', 'На высоте'], ['outdoor', 'Улица'], ['hard_surface', 'Сложная поверхность']]
  const cover = c.sketches.find(f => f.thumb)
  const last = c.feed?.[0]
  return <div className="card dark promo live-card">
    {cover && !compact && <div className="lc-cover" style={{ backgroundImage: `linear-gradient(180deg, rgba(0,0,0,.05), rgba(11,11,13,.92)), url(${cover.thumb})` }}
      onClick={() => setBig(cover)}>
      {cover.approved && <span className="badge ok">утверждённый эскиз</span>}
    </div>}
    <div className="promo-top"><span className="kick">Что предстоит</span>{c.now.length > 0 && <span className="small live-now">● сейчас: {c.now.map(n => n.split(' ')[0]).join(', ')}</span>}</div>
    {!compact && <h2>{c.title}</h2>}
    <div className="lc-addr">
      <p className="small muted">{[c.city, c.address, c.area ? `${m2(c.area)} м²` : ''].filter(Boolean).join(' · ') || 'адрес не указан в сделке'}</p>
      {c.map && <a className="btn mini ghost" href={c.map} target="_blank" rel="noreferrer">Карта 2ГИС</a>}
    </div>
    {zone !== 'print' && <>
      <div className="promo-lvl"><span>Сложность</span><b>{c.complexity ? LV[c.complexity] : 'не указана'}</b>{c.complexity_src && SRC[c.complexity_src] && <i>{SRC[c.complexity_src]}</i>}</div>
      <div className="conds">{conds.map(([k, t]) => <span key={k} className={c[k] ? 'on' : ''}>{c[k] ? '● ' : ''}{t}</span>)}</div></>}
    {c.area ? <div className="lc-prog"><div className="lc-prog-top"><span>Сделано</span><b>{m2(c.done_m2 || 0)} из {m2(c.area)} м²{c.pct != null ? ` · ${c.pct}%` : ''}</b></div>
      <div className="bar"><i style={{ width: (c.pct || 0) + '%' }} /></div></div> : null}
    {c.plan_m2 ? <p className="small">Норма на твою смену — <b>{m2(c.plan_m2)} м²</b></p> : null}
    {c.stages && <div className="lc-stages">{c.stages.map((s, i) => <span key={s.key} className={s.done ? 'done' : ''}><i>{s.done ? '✓' : i + 1}</i>{s.title}</span>)}</div>}
    {c.sketches.length > 0 && <><h3>Эскизы</h3><div className="sketches">{c.sketches.map(f => f.thumb ?
      <button key={f.id} className={'sk' + (f.approved ? ' ok' : '')} onClick={() => setBig(f)}><img src={f.thumb} alt={f.name} loading="lazy" /></button> :
      <a key={f.id} className="sk pdf" href={f.url} target="_blank" rel="noreferrer">PDF<span>{f.name}</span></a>)}</div></>}
    {!c.sketches.length && <p className="small muted">Эскизов пока нет: они появятся сами, когда дизайнер положит их в папку сделки «ДИЗАЙН».</p>}
    {last && (last.before || last.after) && !compact && <><h3>До и после · {last.who.split(' ')[0]}, {new Date(last.at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</h3>
      {last.before && last.after ? <div className="ba">
        <img src={last.after} alt="после" />
        <div className="ba-before" style={{ width: ba + '%' }}><img src={last.before} alt="до" /></div>
        <input type="range" min="0" max="100" value={ba} onChange={e => setBa(+e.target.value)} aria-label="до / после" />
        <span className="ba-l">до</span><span className="ba-r">после</span>
      </div> : <img className="before" src={last.after || last.before} alt="фото смены" />}
      {last.work_done && <p className="small muted">«{last.work_done}»</p>}</>}
    {c.feed?.length > 1 && !compact && <div className="lc-feed">{c.feed.slice(1).map(f => <button key={f.id} onClick={() => setBig({ thumb: f.after || f.before, url: f.after_full || f.before_full, name: f.work_done })}>
      <img src={f.after || f.before} alt="" loading="lazy" /><span>{new Date(f.at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })}</span></button>)}</div>}
    {c.trip && <p className="small trip-note">✈ Командировка: день дороги — кнопкой «Дорога», суточные начислятся сами.</p>}
    <p className="small muted">Условия — из сделки. Не так на объекте — скажи {BOSS[role] || 'Главному художнику'}.</p>
    {big && <div className="lightbox" onClick={() => setBig(null)}><img src={big.url && big.mime?.startsWith('image/') ? big.url : big.thumb} alt={big.name || ''} />
      {big.name && <p>{big.name}{big.path ? ` · ${big.path}` : ''}</p>}<button className="ghost mini">Закрыть</button></div>}
  </div>
}

// Подсказки смены — интерактивный чек-лист: тап отмечает, отметки живут на телефоне до конца смены.
export function Hints({ step, role, cond, v, uid }) {
  const items = hintsFor(step, role, cond, v)
  const key = `artgame.hints.${uid || 'new'}.${step}`
  const [done, setDone] = useState(() => { try { return JSON.parse(localStorage.getItem(key) || '[]') } catch { return [] } })
  const [open, setOpen] = useState(step !== 'run')
  if (!items.length) return null
  const toggle = i => { const n = done.includes(i) ? done.filter(x => x !== i) : [...done, i]; setDone(n); try { localStorage.setItem(key, JSON.stringify(n)) } catch { /* без памяти */ } }
  const n = items.filter((_, i) => done.includes(i)).length
  return <div className={'card hints' + (n === items.length ? ' all' : '')}>
    <button className="hints-head" onClick={() => setOpen(!open)}><span>💡 {HINT_TITLE[step]}</span><b>{n} из {items.length}</b><i>{open ? '▴' : '▾'}</i></button>
    {open && items.map((t, i) => <button key={i} className={'hint' + (done.includes(i) ? ' on' : '')} onClick={() => toggle(i)}><span className="box">{done.includes(i) ? '✓' : ''}</span>{t}</button>)}
  </div>
}

// gallery (HEAD 09.11): в отчётах задним числом фото берут из галереи телефона, а не только с камеры
function Snap({ value, set, label, gallery }) {
  return <label className={'photo snap' + (value ? ' has' : '')}>
    {value ? <img src={value} alt={label} /> : <span>{gallery ? '🖼' : '📷'} {label}</span>}
    <input type="file" accept="image/*" {...(gallery ? {} : { capture: 'environment' })} hidden onChange={async e => e.target.files[0] && set(await shrink(e.target.files[0]))} />
  </label>
}

// Смена по шагам (HEAD 08.11): «Начать» с фото стены до → смена идёт → «Закончить» с фото в конце, м² и «что сделал».
export function ShiftForm({ done }) {
  const d = useDict()
  const [open, setOpen] = useState(loadOpen)
  const [checked, setChecked] = useState(false)
  useEffect(() => {
    api('/shifts/open').then(r => {
      if (r.shift) { const o = { client_uid: r.shift.client_uid, object_id: r.shift.object_id, object_title: r.shift.object_title,
        zone_code: r.shift.zone_code, role: r.shift.role_code, started_at: r.shift.started_at, before: r.shift.photo_before_url,
        workshop: r.shift.kind === 'workshop' ? (r.shift.task || 'Мастерская') : null }; saveOpen(o); setOpen(o) }
      else if (!pending()) { saveOpen(null); setOpen(null) }   // закрыта на сервере, а в очереди ничего нет
    }, () => {}).finally(() => setChecked(true))
  }, [])
  if (!d) return <div className="card muted">Загрузка…</div>
  if (open) return <Running o={open} d={d} done={t => { saveOpen(null); setOpen(null); done(t) }} />
  return <><StartShift d={d} checked={checked} onStarted={o => { saveOpen(o); setOpen(o) }} onRoad={done} />
    {d.backfill?.open && <PastShift d={d} done={done} />}</>
}

// «Прошлая смена» (HEAD 09.11: «чтобы ребята всё заполнили с 1 ноября»): дата, объект (и сданные), часы, м², что сделал,
// фото по возможности → сразу на проверку с пометкой «задним числом». Открыто до даты из настроек сервера.
const dm = x => new Date(x).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
const yday = () => { const t = new Date(); t.setDate(t.getDate() - 1); return t.toISOString().slice(0, 10) }
const tday = () => { const t = new Date(); return new Date(t - t.getTimezoneOffset() * 6e4).toISOString().slice(0, 10) }
function PastShift({ d, done }) {
  const b = d.backfill
  const [open, setOpen] = useState(false)
  const [v, set] = useState({ object_id: b.objects[0]?.id, zone_code: d.zones[0], day: '', start_time: '09:00', end_time: '19:00', plus: '', area_m2: '', work_done: '', workshop: '' })
  const shop = !!v.workshop   // мастерская без проекта (печать, HEAD 09.11)
  const [pics, setPics] = useState([])     // сколько угодно фото из галереи (HEAD 09.11)
  const [busy, setBusy] = useState(false)
  const [prog, setProg] = useState('')
  const [err, setErr] = useState('')
  const pick = async files => {
    for (const f of [...files]) { const x = await shrink(f); setPics(a => [...a, x]) }
  }
  // Часы считаем из «начали» и «закончили» (Диана 11.11 ввела конец «1930» в поле часов)
  const hm = t => { const m = String(t || '').trim().match(/^(\d{1,2})(?:[:.\s,-]?(\d{2}))?$/); return m && +m[1] < 24 && +(m[2] || 0) < 60 ? +m[1] * 60 + +(m[2] || 0) : null }
  const a = hm(v.start_time), z = hm(v.end_time)
  const late = v.plus === '' ? (a != null && z != null && z <= a ? 1 : 0) : +v.plus   // конец раньше начала — значит, на следующий день
  const hours = a == null || z == null ? 0 : Math.round((z - a + late * 1440) / 6) / 10
  const tooLong = hours > 48
  const send = async () => {
    if (tooLong) { setErr('Одной записью — до 48 часов. Дольше — внесите по дням.'); return }
    setBusy(true); setErr('')
    try {
      const sh = await api('/shifts/past', { method: 'POST', body: { client_uid: uuid(), ...v, ...(shop ? { object_id: 0, zone_code: 'print' } : { workshop: null }),
        hours, end_time: undefined, plus: undefined, area_m2: v.area_m2 === '' || shop ? null : +v.area_m2, photo_after: shop ? null : pics[0] || null } })
      const rest = shop ? [] : pics.slice(1)
      let bad = 0
      for (let i = 0; i < rest.length; i++) {
        setProg(`Фото ${i + 2} из ${pics.length}…`)
        try { await api(`/shifts/${sh.id}/photos`, { method: 'POST', body: { client_uid: uuid(), photo: rest[i] } }) } catch { bad++ }
      }
      done(`Смена за ${dm(v.day)} ушла на проверку${pics.length && !shop ? `, фото: ${pics.length - bad}` : ''}.${bad ? ` Не загрузилось ${bad} — добавь их в «Кабинете» → «Мои смены».` : ''}`)
    } catch (e) { setErr(e.message || String(e)) } finally { setBusy(false); setProg('') }
  }
  return <div className="card past">
    <div className="head" onClick={() => setOpen(!open)} style={{ cursor: 'pointer' }}>
      <div><h3>Прошлая смена</h3><p className="small muted">Смены за дни с {dm(b.from)} по сегодня — если смена уже закончилась. Вносить можно до {dm(b.until)} включительно.</p></div>
      <button className="ghost mini">{open ? 'Свернуть' : 'Внести'}</button></div>
    {open && <>
      <label className="muted">Дата</label><input type="date" min={b.from} max={tday()} value={v.day} onChange={e => set({ ...v, day: e.target.value })} />
      {d.workshop && <div className="segf"><button className={shop ? '' : 'on'} onClick={() => set({ ...v, workshop: '' })}>На объекте</button>
        <button className={shop ? 'on' : ''} onClick={() => set({ ...v, workshop: d.workshop[0] })}>Мастерская · без проекта</button></div>}
      {shop ? <><label className="muted">Что делал</label>
        <div className="chips">{d.workshop.map(t => <button key={t} className={v.workshop === t ? 'on' : ''} onClick={() => set({ ...v, workshop: t })}>{t}</button>)}</div></> : <>
      <label className="muted">Объект</label>
      <select value={v.object_id} onChange={e => set({ ...v, object_id: +e.target.value })}>
        {b.objects.map(o => <option key={o.id} value={o.id}>№{o.id} · {o.title}{o.city ? ` — ${o.city}` : ''}</option>)}
      </select>
      {d.zones.length > 1 && <div className="segf">{d.zones.map(z => <button key={z} className={v.zone_code === z ? 'on' : ''} onClick={() => set({ ...v, zone_code: z })}>{ZONE[z]}</button>)}</div>}</>}
      <div className="pair"><div><label className="muted">Начали в</label><input type="time" value={v.start_time} onChange={e => set({ ...v, start_time: e.target.value })} /></div>
        <div><label className="muted">Закончили в</label><input type="time" value={v.end_time} onChange={e => set({ ...v, end_time: e.target.value })} /></div></div>
      <div className="segf">{['тот же день', 'следующий', 'через день'].map((t, i) => <button key={i} className={late === i ? 'on' : ''} onClick={() => set({ ...v, plus: String(i) })}>{t}</button>)}</div>
      <p className={'small ' + (tooLong || !hours ? 'why' : 'muted')}>{a == null || z == null ? 'Укажите время начала и конца, например 09:00 и 19:30.' : !hours ? 'Конец совпадает с началом — проверьте время.' : `Получается ${String(hours).replace('.', ',')} ч.${tooLong ? ' Одной записью — до 48 часов, дольше — внесите по дням.' : ''}`}</p>
      <p className="small muted">Был на двух объектах за день — внеси каждую смену отдельно, со своим временем.</p>
      <p className="small muted">Сверх {d.shift_hours || 10} ч — по часовой ставке, ночные часы ({d.night || '22:00–6:00'}) — +{d.night_pct ?? 10}% к часу. Посчитается само.</p>
      {!shop && <><label className="muted">Сделано, м²</label><input inputMode="decimal" value={v.area_m2} onChange={e => set({ ...v, area_m2: e.target.value.replace(',', '.').replace(/[^\d.]/g, '') })} /></>}
      <label className="muted">Что сделал</label><textarea value={v.work_done} onChange={e => set({ ...v, work_done: e.target.value })} placeholder="Фон, контур, детали…" />
      {!shop && <><label className="muted">Фото работы · {pics.length ? `выбрано ${pics.length}` : 'из галереи, сколько угодно'}</label>
        <div className="pics">{pics.map((x, i) => <span key={i}><img src={x} alt="" /><button className="ghost mini" onClick={() => setPics(pics.filter((_, j) => j !== i))}>✕</button></span>)}
          <label className="photo snap add"><span>🖼 Добавить фото</span><input type="file" accept="image/*" multiple hidden onChange={e => { pick(e.target.files); e.target.value = '' }} /></label></div></>}
      {prog && <p className="small muted">{prog}</p>}
      <button disabled={busy || !v.day || (!shop && !v.object_id) || !hours || tooLong || v.work_done.trim().length < 3} onClick={send}>{busy ? 'Отправляю…' : 'Отправить на проверку'}</button>
      {err && <p className="small why">{err}</p>}
    </>}
  </div>
}

// День дороги в командировку (HEAD 08.11): одна кнопка; оплата — как смена по ставке роли, суточные — сами (pay.trip_food).
function Road({ obj, zone, done }) {
  const [dir, setDir] = useState('there')
  const [ticket, setTicket] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const go = async () => {
    setBusy(true); setErr('')
    try {
      const was = failed().length
      const left = await enqueue('/shifts/road', { object_id: obj.id, zone_code: zone, day: new Date().toISOString(), direction: dir, ticket: ticket || null })
      const f = failed()
      if (f.length > was && f[0].path === '/shifts/road') { setErr(`Сервер не принял: ${f[0].error}`); return }
      done(left ? 'Дорога сохранена на телефоне, отправится, когда будет сеть.' : 'День дороги отмечен и ушёл на проверку.')
    } catch (e) { setErr(e.message || String(e)) } finally { setBusy(false) }
  }
  return <div className="card road">
    <h3>✈ Сегодня в дороге?</h3>
    <p className="small muted">Объект в другом городе — день дороги оплачивается как смена, суточные начисляются сами.</p>
    <div className="segf"><button className={dir === 'there' ? 'on' : ''} onClick={() => setDir('there')}>На объект</button>
      <button className={dir === 'back' ? 'on' : ''} onClick={() => setDir('back')}>Обратно</button></div>
    <Snap value={ticket} set={setTicket} label="Билет или чек (по желанию)" />
    <button className="dark" disabled={busy} onClick={go}>{busy ? 'Отмечаю…' : 'Отметить день дороги'}</button>
    {err && <p className="small why">{err}</p>}
  </div>
}

// «Мастерская» без проекта (HEAD 09.11): печать — ТО принтера, ремонт, тест печати, обучение. Без фото, оплата по часам.
function Workshop({ d, onStarted, back }) {
  const [task, setTask] = useState(d.workshop[0])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const zone = d.zones.includes('print') ? 'print' : d.zones[0]
  const start = async () => {
    setBusy(true); setErr('')
    try {
      const o = { client_uid: uuid(), object_id: 0, object_title: 'Мастерская · ' + task, zone_code: zone, started_at: new Date().toISOString(), workshop: task }
      const was = failed().length
      await enqueue('/shifts/start', { client_uid: o.client_uid, object_id: 0, zone_code: zone, started_at: o.started_at, workshop: task })
      const f = failed()
      if (f.length > was && f[0].path === '/shifts/start') { setErr(`Сервер не принял: ${f[0].error}`); return }
      onStarted(o)
    } catch (e) { setErr(`Не получилось начать: ${e.message || e}`) } finally { setBusy(false) }
  }
  return <div className="card workshop">
    <div className="steps"><span className="on">1 Начало</span><span>2 Работа</span><span>3 Конец смены</span></div>
    <h2>Смена в мастерской</h2>
    <p className="small muted">Без проекта: оплачивается как смена по часам, без плана и бонуса. Проверяет Мастер печати или HEAD.</p>
    <label className="muted">Что делаешь</label>
    <div className="chips">{d.workshop.map(t => <button key={t} className={task === t ? 'on' : ''} onClick={() => setTask(t)}>{t}</button>)}</div>
    <button disabled={busy} onClick={start}>{busy ? 'Начинаю…' : 'Начать смену в мастерской'}</button>
    {err && <p className="small why">{err}</p>}
    {back && <p className="small"><a onClick={back}>← на объект</a></p>}
  </div>
}

function StartShift(props) {
  const { d } = props
  const [mode, setMode] = useState('obj')
  if (!d.workshop) return <StartObject {...props} />
  return <>
    <div className="segf"><button className={mode === 'obj' ? 'on' : ''} onClick={() => setMode('obj')}>На объекте</button>
      <button className={mode === 'shop' ? 'on' : ''} onClick={() => setMode('shop')}>Мастерская · без проекта</button></div>
    {mode === 'shop' ? <Workshop d={d} onStarted={props.onStarted} /> : <StartObject {...props} />}
  </>
}

function StartObject({ d, onStarted, onRoad }) {
  const objs = d.objects.filter(o => o.id)
  const [v, set] = useState({ object_id: objs[0]?.id, zone_code: d.zones[0] })
  const [photo, setPhoto] = useState('')
  const [busy, setBusy] = useState(false)
  const [cond, setCond] = useState({})
  const [err, setErr] = useState('')
  const looking = viewAs() && !testAs()   // HEAD смотрит как сотрудник: только просмотр — предложить тест
  if (!objs.length) return <div className="card"><h2>Смена</h2><p className="muted">Сейчас нет объектов в работе. Когда МОП переведёт сделку в «Выполнение проекта», объект появится здесь.{d.workshop ? ' Работа без проекта — «Мастерская».' : ''}</p></div>
  const obj = objs.find(o => o.id === v.object_id) || objs[0]
  // две роли (HEAD 08.11): роль смены — по зоне объекта (печать → роль печати, роспись → роль художника), можно сменить
  const roles = d.roles || [d.role]
  const auto = (() => { const p = roles.filter(r => PRINT_ROLES.includes(r) === (v.zone_code === 'print')); return p.includes(d.role) || !p.length ? d.role : p[0] })()
  const role = v.role && roles.includes(v.role) ? v.role : auto
  // геолокация не держит кнопку дольше 5 с (в Telegram запрос доступа может не ответить вовсе)
  const where = () => new Promise(r => {
    const t = setTimeout(() => r(null), 5000)
    try { navigator.geolocation ? navigator.geolocation.getCurrentPosition(p => { clearTimeout(t); r(p.coords) }, () => { clearTimeout(t); r(null) }, { timeout: 4000 }) : r(null) }
    catch { clearTimeout(t); r(null) }
  })
  const start = async () => {
    setBusy(true); setErr('')
    try {
      const geo = await where()
      const o = { client_uid: uuid(), object_id: obj.id, object_title: obj.title, zone_code: v.zone_code, started_at: new Date().toISOString(), before: photo, role }
      const was = failed().length
      await enqueue('/shifts/start', { client_uid: o.client_uid, object_id: o.object_id, zone_code: o.zone_code, started_at: o.started_at, photo_before: photo,
        geo_lat: geo?.latitude ?? null, geo_lon: geo?.longitude ?? null, ...(roles.length > 1 ? { role } : {}) })
      const f = failed()
      if (f.length > was && f[0].path === '/shifts/start') { setErr(`Сервер не принял: ${f[0].error}`); return }   // 4xx — не делаем вид, что смена идёт
      onStarted(o)
    } catch (e) {
      setErr(e.status === 403 && looking ? 'Это режим просмотра — смену отсюда не начать.' : `Не получилось начать: ${e.message || e}`)
    } finally { setBusy(false) }
  }
  return <>
    <div className="card">
      <div className="steps"><span className="on">1 Начало</span><span>2 Работа</span><span>3 Конец смены</span></div>
      <h2>Начать смену</h2>
      <label className="muted">Объект</label>
      <div className="objpick">{objs.map(o => <button key={o.id} className={o.id === obj.id ? 'on' : ''} onClick={() => set({ ...v, object_id: o.id })}>
        <b>№{o.id}</b> {o.title}{o.city ? <span> · {o.city}</span> : null}</button>)}</div>
      {d.zones.length > 1 && <div className="segf">{d.zones.map(z => <button key={z} className={v.zone_code === z ? 'on' : ''} onClick={() => set({ ...v, zone_code: z, role: null })}>{ZONE[z]}</button>)}</div>}
      {roles.length > 1 && <><label className="muted">Роль на смене — по ней ставка</label>
        <div className="chips">{roles.map(r => <button key={r} className={role === r ? 'on' : ''} onClick={() => set({ ...v, role: r })}>{ROLE_T[r] || r}</button>)}</div>
        {role === auto && <p className="small muted">Подставлено по объекту: {ZONE[v.zone_code]}.</p>}</>}
    </div>
    <Promo id={obj.id} zone={v.zone_code} compact={false} onData={setCond} role={role} />
    {cond.trip && <Road obj={obj} zone={v.zone_code} done={onRoad} />}
    <Hints step="start" role={role} cond={cond} v={d.safety || {}} uid={'start-' + obj.id} />
    <div className="card">
      <h3>Фото стены до начала</h3>
      <Snap value={photo} set={setPhoto} label="Сфотографировать стену" />
      {looking && <div className="warnbox">Вы смотрите как сотрудник — это только просмотр, смена не начнётся.
        {d.role && <button className="mini" style={{ marginTop: 8 }} onClick={() => startViewAs('test:' + d.role)}>Пройти как сотрудник · тест</button>}</div>}
      <button disabled={!photo || busy} onClick={start}>{busy ? 'Начинаю…' : 'Начать смену'}</button>
      {err && <p className="small why">{err}</p>}
      {!photo && <p className="small muted">Без фото «до» смену не начать: по нему Главный художник видит, что сделано за день.</p>}
    </div>
  </>
}

function Running({ o, d, done }) {
  const [now, setNow] = useState(Date.now())
  const [v, set] = useState({ area_m2: '', work_done: '', note: '', printer: d.printer || '', stage: '' })
  const [photo, setPhoto] = useState('')
  const [busy, setBusy] = useState(false)
  const [cond, setCond] = useState({})
  const stages = d.stages || []
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 30000); return () => clearInterval(t) }, [])
  const print = o.zone_code === 'print'
  const shop = !!o.workshop
  const ok = (photo || shop) && v.work_done.trim().length >= 3
  const finish = async () => {
    setBusy(true)
    try {
      const left = await enqueue('/shifts/finish', { client_uid: o.client_uid, ended_at: new Date().toISOString(), area_m2: v.area_m2 === '' ? null : +v.area_m2,
        work_done: v.work_done.trim(), photo_after: photo || null, note: v.note || null, printer: print ? v.printer || null : null, stage: v.stage || null })
      done(left ? 'Сохранено на телефоне, отправится, когда будет сеть.' : 'Смена закончена и ушла на проверку.')
    } catch { setBusy(false) }
  }
  const cancel = () => { if (confirm('Отменить смену? Она не уйдёт на проверку.')) api('/shifts/open').then(r => r.shift && api(`/shift/${r.shift.id}/cancel`, { method: 'POST' })).finally(() => done('Смена отменена.')) }
  return <>
    <div className="card dark live">
      <div className="steps dark"><span className="done">1 Начало</span><span className="on">2 Работа</span><span>3 Конец смены</span></div>
      <span className="kick">Смена идёт</span>
      <div className="timer">{hm(now - new Date(o.started_at).getTime())}</div>
      <p className="small muted">с {new Date(o.started_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })} · {shop ? o.object_title : `№${o.object_id} ${o.object_title} · ${ZONE[o.zone_code]}`}</p>
      {o.before && <img className="before" src={o.before} alt="стена до" />}
    </div>
    {!shop && <Promo id={o.object_id} zone={o.zone_code} compact onData={setCond} role={o.role || d.role} />}
    {!shop && <Hints step="run" role={o.role || d.role} cond={cond} v={d.safety || {}} uid={o.client_uid} />}
    <div className="card">
      <h2>Закончить смену</h2>
      {!shop && <><label className="muted">{print ? 'Напечатано, м²' : 'Сделано, м²'}</label>
      <input inputMode="decimal" value={v.area_m2} onChange={e => set({ ...v, area_m2: e.target.value.replace(',', '.') })} placeholder="например, 4,5" /></>}
      <label className="muted">Что сделал за смену</label>
      <textarea rows="3" value={v.work_done} onChange={e => set({ ...v, work_done: e.target.value })} placeholder={shop ? 'Например: прочистка головы, замена демпферов, тест-печать' : 'Например: загрунтовал стену, перенёс эскиз, прописал фон слева'} />
      {print && <><label className="muted">Принтер</label><input value={v.printer} onChange={e => set({ ...v, printer: e.target.value })} placeholder="Название принтера" /></>}
      <input placeholder="Комментарий (по желанию)" value={v.note} onChange={e => set({ ...v, note: e.target.value })} />
      {!print && !shop && stages.length > 0 && <><label className="muted">Какой этап закрыл сегодня</label>
        <div className="chips stagepick">{stages.map(s => <button key={s.key} className={v.stage === s.key ? 'on' : 'ghost'} onClick={() => set({ ...v, stage: v.stage === s.key ? '' : s.key })}>{s.title}</button>)}</div></>}
      {!shop && <><Hints step="finish" role={o.role || d.role} cond={{ ...cond, handover: v.stage === 'handover' }} v={d.safety || {}} uid={o.client_uid} />
      <h3>Фото в конце смены</h3>
      <Snap value={photo} set={setPhoto} label="Сфотографировать результат" /></>}
      <button disabled={!ok || busy} onClick={finish}>{busy ? 'Отправляю…' : 'Закончить и отправить на проверку'}</button>
      {!ok && <p className="small muted">{shop ? 'Напиши пару слов, что сделано.' : 'Нужно фото в конце смены и пара слов, что сделано.'}</p>}
      <p className="small"><a onClick={cancel}>Отменить смену</a></p>
    </div>
  </>
}

export function ExpenseForm({ done }) {
  const d = useDict()
  const [v, set] = useState(null)
  const [busy, setBusy] = useState(false)
  const [uid] = useState(uuid)   // один расход = один client_uid: повторное нажатие не создаёт дубль (Звягина 10.11)
  useEffect(() => { if (d) set({ object_id: d.objects[0]?.id, zone_code: d.zones[0], category: d.categories[0]?.code, amount: '', paid_by: 'own', note: '' }) }, [d])
  if (!d || !v) return <div className="card muted">Загрузка…</div>
  const past = !!v.day
  const objs = past ? d.backfill.objects : d.objects
  const send = async () => {
    if (busy) return
    setBusy(true)
    try {
      const left = await enqueue('/expenses', { ...v, client_uid: uid, amount: +v.amount, day: v.day || null })
      done(left ? 'Сохранено на телефоне, отправится, когда будет сеть.' : 'Расход отправлен на проверку.')
    } catch (e) { setBusy(false); throw e }
  }
  return <div className="card">
    <h2>Расход</h2>
    {d.backfill?.open && <><div className="segf"><button className={past ? '' : 'on'} onClick={() => set({ ...v, day: '', object_id: d.objects[0]?.id })}>Сегодня</button>
      <button className={past ? 'on' : ''} onClick={() => set({ ...v, day: yday(), object_id: d.backfill.objects[0]?.id })}>Прошлая дата</button></div>
      {past && <><p className="small muted">Расходы с {dm(d.backfill.from)} можно внести до {dm(d.backfill.until)}.</p>
        <input type="date" min={d.backfill.from} max={yday()} value={v.day} onChange={e => set({ ...v, day: e.target.value })} /></>}</>}
    <Common d={{ ...d, objects: objs }} v={v} set={set} />
    <label className="muted">Категория</label>
    <select value={v.category} onChange={e => set({ ...v, category: e.target.value })}>
      {d.categories.map(c => <option key={c.code} value={c.code}>{c.title}</option>)}
    </select>
    <label className="muted">Сумма, ₸</label><input inputMode="numeric" value={v.amount} onChange={e => set({ ...v, amount: e.target.value.replace(/\D/g, '') })} />
    <div className="seg">
      <button className={v.paid_by === 'own' ? '' : 'ghost'} onClick={() => set({ ...v, paid_by: 'own' })}>Свои деньги</button>
      <button className={v.paid_by === 'company' ? '' : 'ghost'} onClick={() => set({ ...v, paid_by: 'company' })}>Компании</button>
    </div>
    <p className="small muted">{v.paid_by === 'own' ? 'Свои деньги: после одобрения чек «к выплате», возвращаем в понедельник вместе с выплатами.' : 'Деньги компании: платили картой или наличными компании, тебе возвращать нечего.'}</p>
    <input placeholder="Комментарий" value={v.note} onChange={e => set({ ...v, note: e.target.value })} />
    <Receipt value={v.receipt} pick={async f => set({ ...v, receipt: await shrink(f) })} />
    <button disabled={!v.amount || busy} onClick={send}>{busy ? 'Отправляю…' : 'Отправить расход'}</button>
  </div>
}

// Доп. фото отчёта задним числом (HEAD 09.11)
export function More({ x }) {
  if (!x.photos?.length) return null
  return <div className="pics view">{x.photos.map((f, i) => <a key={i} href={f.full} target="_blank" rel="noreferrer"><img src={f.url} alt="" /></a>)}</div>
}

// Добавить ещё фото к отчёту задним числом, пока он на проверке
function AddPics({ id, done }) {
  const [msg, setMsg] = useState('')
  const up = async files => {
    let ok = 0
    for (const f of [...files]) {
      setMsg(`Загружаю ${ok + 1} из ${files.length}…`)
      try { await api(`/shifts/${id}/photos`, { method: 'POST', body: { client_uid: uuid(), photo: await shrink(f) } }); ok++ } catch { /* следующее */ }
    }
    setMsg(`Добавлено фото: ${ok}`); done()
  }
  return <label className="small addpics"><a>🖼 Добавить фото</a><input type="file" accept="image/*" multiple hidden onChange={e => { const f = [...e.target.files]; e.target.value = ''; up(f) }} />{msg && <span className="muted"> {msg}</span>}</label>
}

export function Mine() {
  const [m, setM] = useState(null)
  const [re, setRe] = useState(0)        // обращение подано — обновить список обращений
  const [note, setNote] = useState('')
  const load = () => api('/my').then(setM, () => {})
  useEffect(() => {
    flush(); load()
    window.addEventListener('artgame:queue', load)
    return () => window.removeEventListener('artgame:queue', load)
  }, [])
  if (!m) return <div className="card muted">Загрузка…</div>
  const cancel = (k, id) => api(`/${k}/${id}/cancel`, { method: 'POST' }).then(load)
  return <>
    {pending() > 0 && <div className="card">Ждут сети: {pending()}</div>}
    {failed().length > 0 && <div className="card"><h3>Не принято сервером</h3>
      {failed().map((x, i) => <div key={i} className="row"><div><b>{x.amount ? money(x.amount) : x.path}</b>{x.note ? ` · ${x.note}` : ''}
        <div className="small why">{x.error}</div></div></div>)}
      <button className="ghost mini" onClick={() => { clearFailed(); load() }}>Понятно, скрыть</button></div>}
    {note && <div className="card">{note}</div>}
    <Appeals reload={re} />
    <div className="card"><h2>Мои смены</h2>
      {m.shifts.length ? m.shifts.map(s => <div key={s.id} className="row">
        <div><b>{s.object_title}</b><br /><span className="muted small">{when(s.started_at, s.ended_at)}{s.area_m2 ? ` · ${+s.area_m2} м²` : ''}{s.backfill ? ' · задним числом' : ''}</span>
          {s.plan_m2 && <div className="small">{s.zone_code === 'print' ? 'План' : 'Норма'} {m2(s.plan_m2)} м²{s.kpd != null && <> · КПД <b>{pct(s.kpd)}</b></>}{+s.bonus > 0 && <> · бонус <b>{money(s.bonus)}</b></>}</div>}
          {s.work_done && <div className="small">Сделал: {s.work_done}</div>}
          {(s.photo_before_url || s.photo_after_url) && <div className="pair">{s.photo_before_url && <img src={s.photo_before_url} alt="до" />}{s.photo_after_url && <img src={s.photo_after_url} alt="после" />}</div>}
          <More x={s} />
          {s.backfill && s.status === 'submitted' && s.object_id ? <AddPics id={s.id} done={load} /> : null}
          {s.reason && <div className="small">Причина: {s.reason}</div>}
          <CurMark x={s} />
          {['submitted', 'approved', 'rejected'].includes(s.status) && <FixAppeal k="shift" x={s} done={t => { setNote(t); setRe(n => n + 1) }} />}</div>
        <StatusMark status={s.status} />
        {s.status === 'submitted' && <a onClick={() => cancel('shift', s.id)}>отменить</a>}
      </div>) : <p className="muted">Пока нет</p>}
    </div>
    <div className="card"><h2>Мои расходы</h2>
      {m.expenses.length ? m.expenses.map(e => <div key={e.id} className="row">
        <div><b>{money(e.amount)}</b> · {e.object_title}{e.backfill ? <span className="small muted"> · {new Date(e.created_at).toLocaleDateString('ru-RU')}, задним числом</span> : null}<br /><span className="muted small">{e.payout_status === 'to_pay' ? 'к выплате' : e.payout_status === 'paid' ? 'выплачено' : ''}</span>
          {e.receipt_url && <a href={e.receipt_url} target="_blank" rel="noreferrer"> чек</a>}
          {e.reason && <div className="small">Причина: {e.reason}</div>}
          <CurMark x={e} />
          {['submitted', 'approved', 'rejected'].includes(e.status) && <FixAppeal k="expense" x={e} done={t => { setNote(t); setRe(n => n + 1) }} />}</div>
        <StatusMark status={e.status} />
        {e.status === 'submitted' && <a onClick={() => cancel('expense', e.id)}>отменить</a>}
      </div>) : <p className="muted">Пока нет</p>}
    </div>
  </>
}

// Проверяющий сам правит смену до решения (HEAD 09.11): время начала, часы через полночь, «дорога» → «смена»
const clockAt = d => new Date(d).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Almaty' })
function FixShift({ x, done }) {
  const hrs = x.ended_at ? Math.round((new Date(x.ended_at) - new Date(x.started_at)) / 36e5 * 10) / 10 : 10
  const [open, setOpen] = useState(false)
  const [v, set] = useState({ start_time: clockAt(x.started_at), hours: String(hrs), kind: x.kind || 'work' })
  const [err, setErr] = useState('')
  if (!open) return <a className="small fixlink" onClick={() => setOpen(true)}>✎ Исправить время{x.kind === 'road' ? ' или тип' : ''}</a>
  const save = () => api(`/shift/${x.id}/fix`, { method: 'POST', body: { start_time: v.start_time, hours: +v.hours, kind: v.kind } })
    .then(() => { setOpen(false); done() }, e => setErr(e.message))
  return <div className="fixbox">
    <div className="pair"><div><label className="muted small">Начали в</label><input type="time" value={v.start_time} onChange={e => set({ ...v, start_time: e.target.value })} /></div>
      <div><label className="muted small">Часов (до 48)</label><input inputMode="decimal" value={v.hours} onChange={e => set({ ...v, hours: e.target.value.replace(',', '.').replace(/[^\d.]/g, '') })} /></div></div>
    {x.kind === 'road' && <div className="segf"><button className={v.kind === 'road' ? 'on' : ''} onClick={() => set({ ...v, kind: 'road' })}>Дорога</button>
      <button className={v.kind === 'work' ? 'on' : ''} onClick={() => set({ ...v, kind: 'work' })}>Рабочая смена</button></div>}
    <p className="small muted">Через полночь — просто больше часов: 9:00 + 18 ч = до 3:00. Ночь и переработка посчитаются сами.</p>
    {err && <p className="small why">{err}</p>}
    <div className="seg"><button className="mini" disabled={!(+v.hours > 0 && +v.hours <= 48)} onClick={save}>Сохранить</button><button className="ghost mini" onClick={() => setOpen(false)}>Отмена</button></div>
  </div>
}

// ---------- Проверка в две ступени и обращения (HEAD 11.11) ----------
// Куратор (ГИП объекта или старший по зоне) ставит 1–5★ и комментарий, расходу — «верно / есть вопрос». Утверждает HEAD.
const STARS = n => '★★★★★'.slice(0, n) + '☆☆☆☆☆'.slice(0, 5 - n)
export function CurMark({ x }) {
  if (!x.cur_at) return null
  const bad = x.cur_stars ? x.cur_stars <= 2 : x.cur_ok === false
  return <div className={'small curmark' + (bad ? ' why' : '')}><b className="stars">{x.cur_stars ? STARS(x.cur_stars) : x.cur_ok ? '✓ верно' : '⚠ есть вопрос'}</b>
    {' '}{x.cur_name || 'Куратор'}{x.cur_note ? `: ${x.cur_note}` : ''}</div>
}
function RateBox({ path, stars, done }) {
  const [v, set] = useState({ stars: 0, ok: null, note: '' })
  const [err, setErr] = useState('')
  const need = stars ? v.stars > 0 && v.stars <= 2 : v.ok === false
  const can = (stars ? v.stars > 0 : v.ok !== null) && (!need || v.note.trim())
  const send = () => api(path, { method: 'POST', body: stars ? { stars: v.stars, note: v.note } : { ok: v.ok, note: v.note } }).then(done, e => setErr(e.message))
  return <div className="ratebox">
    {stars ? <div className="starpick" role="group" aria-label="Оценка смены">{[1, 2, 3, 4, 5].map(n =>
      <button key={n} className={n <= v.stars ? 'on' : ''} aria-label={`${n} из 5`} onClick={() => set({ ...v, stars: n })}>★</button>)}</div>
      : <div className="segf"><button className={v.ok === true ? 'on' : ''} onClick={() => set({ ...v, ok: true })}>✓ Верно</button>
        <button className={v.ok === false ? 'on' : ''} onClick={() => set({ ...v, ok: false })}>⚠ Есть вопрос</button></div>}
    <textarea value={v.note} onChange={e => set({ ...v, note: e.target.value })} rows={2}
      placeholder={need ? 'Обязательно: что не так' : 'Комментарий для HEAD (по желанию)'} />
    {err && <p className="small why">{err}</p>}
    <button className="mini" disabled={!can} onClick={send}>Оценить</button>
  </div>
}

const AK = { shift_late: 'Не внёс смену', expense_late: 'Не внёс расход', shift_fix: 'Ошибка в смене', expense_fix: 'Ошибка в расходе' }
const FIELD = { start_time: 'начало', hours: 'часов', area_m2: 'м²', work_done: 'сделал', amount: 'сумма', note: 'комментарий' }
const fv = (k, x) => x == null || x === '' ? '—' : k === 'amount' ? money(x) : k === 'hours' ? String(x).replace('.', ',') + ' ч' : String(x)
const dshort = x => new Date(x).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
export function AppealView({ a }) {
  const d = a.data || {}
  return <>
    <div><b>{AK[a.kind]}</b> · {dshort(a.day)} · {a.object_title}{a.closed && <span className="tag draft">месяц закрыт</span>}</div>
    <div className="small">Почему: {a.why}</div>
    {a.old ? <div className="small">{Object.keys(d).map(k => <div key={k}>{FIELD[k] || k}: <s className="muted">{fv(k, a.old[k])}</s> → <b>{fv(k, d[k])}</b></div>)}
      {a.old.status === 'rejected' && <div className="muted">запись была отклонена</div>}</div>
      : a.kind === 'shift_late' ? <div className="small">с {d.start_time}, {fv('hours', d.hours)}{d.area_m2 ? ` · ${d.area_m2} м²` : ''}{d.workshop ? ` · ${d.workshop}` : ''} · {d.work_done}</div>
      : <div className="small">{money(d.amount)} · {a.category_title || d.category} · {d.paid_by === 'own' ? 'свои' : 'компании'}{d.note ? ` · ${d.note}` : ''}
        {a.receipt_url ? <> · <a href={a.receipt_url} target="_blank" rel="noreferrer">чек</a></> : ' · без чека'}</div>}
    {a.photo_url && <div className="pair"><a href={a.photo_full} target="_blank" rel="noreferrer"><img src={a.photo_url} alt="фото" /></a></div>}
  </>
}

// «Ошибка? Обращение» у своей смены / расхода: что исправить + почему. Пока HEAD не утвердил, запись не меняется.
function FixAppeal({ k, x, done }) {
  const hrs = x.ended_at ? Math.round((new Date(x.ended_at) - new Date(x.started_at)) / 36e5 * 10) / 10 : ''
  const [open, setOpen] = useState(false)
  const [v, set] = useState(k === 'shift' ? { start_time: x.started_at ? clockAt(x.started_at) : '', hours: String(hrs), area_m2: x.area_m2 != null ? String(+x.area_m2) : '', work_done: x.work_done || '' }
    : { amount: String(+x.amount), note: x.note || '' })
  const [why, setWhy] = useState('')
  const [err, setErr] = useState('')
  if (!open) return <a className="small fixlink" onClick={() => setOpen(true)}>Ошибка? Обращение</a>
  const num = t => t.replace(',', '.').replace(/[^\d.]/g, '')
  const send = () => {
    const body = k === 'shift' ? { start_time: v.start_time || null, hours: v.hours ? +v.hours : null, area_m2: v.area_m2 === '' ? null : +v.area_m2, work_done: v.work_done }
      : { amount: v.amount ? +v.amount : null, note: v.note }
    api('/appeals', { method: 'POST', body: { client_uid: uuid(), kind: k + '_fix', target_id: x.id, why, ...body } })
      .then(() => { setOpen(false); done('Обращение ушло: сначала куратору, потом HEAD.') }, e => setErr(e.message))
  }
  return <div className="fixbox">
    <p className="small muted">Напиши, как правильно. Пока HEAD не утвердит, запись не меняется.</p>
    {k === 'shift' ? <>
      <div className="pair"><div><label className="muted small">Начали в</label><input type="time" value={v.start_time} onChange={e => set({ ...v, start_time: e.target.value })} /></div>
        <div><label className="muted small">Часов (до 48)</label><input inputMode="decimal" value={v.hours} onChange={e => set({ ...v, hours: num(e.target.value) })} /></div></div>
      {x.object_id ? <><label className="muted small">Сделано, м²</label><input inputMode="decimal" value={v.area_m2} onChange={e => set({ ...v, area_m2: num(e.target.value) })} /></> : null}
      <label className="muted small">Что сделал</label><textarea rows={2} value={v.work_done} onChange={e => set({ ...v, work_done: e.target.value })} />
    </> : <>
      <label className="muted small">Сумма, ₸</label><input inputMode="decimal" value={v.amount} onChange={e => set({ ...v, amount: num(e.target.value) })} />
      <label className="muted small">Комментарий</label><input value={v.note} onChange={e => set({ ...v, note: e.target.value })} />
    </>}
    <label className="muted small">Почему ошибся</label><textarea rows={2} value={why} onChange={e => setWhy(e.target.value)} placeholder="Например: работал до 21:00, а записал до 19:00" />
    {err && <p className="small why">{err}</p>}
    <div className="seg"><button className="mini" disabled={why.trim().length < 5} onClick={send}>Отправить</button><button className="ghost mini" onClick={() => setOpen(false)}>Отмена</button></div>
  </div>
}

// «Не внёс вовремя»: смена или расход за прошедший день (до 60 дней) — через обращение.
function LateAppeal({ d, done, close }) {
  const [kind, setKind] = useState('shift_late')
  const objs = d.backfill?.objects?.length ? d.backfill.objects : d.objects.filter(o => o.id)
  const [v, set] = useState({ day: '', object_id: objs[0]?.id, zone_code: d.zones[0], start_time: '09:00', hours: '10', area_m2: '', work_done: '',
    workshop: '', amount: '', category: d.categories[0]?.code, paid_by: 'own', note: '' })
  const [why, setWhy] = useState('')
  const [pic, setPic] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const shop = kind === 'shift_late' && !!v.workshop
  const num = t => t.replace(',', '.').replace(/[^\d.]/g, '')
  const min = (() => { const t = new Date(); t.setDate(t.getDate() - 60); return t.toISOString().slice(0, 10) })()
  const ok = v.day && why.trim().length >= 5 && (kind === 'shift_late' ? +v.hours > 0 && +v.hours <= 48 && v.work_done.trim().length >= 3 && (shop || v.object_id) : +v.amount > 0)
  const send = async () => {
    setBusy(true); setErr('')
    const base = { client_uid: uuid(), kind, why, day: v.day, object_id: shop ? 0 : v.object_id, zone_code: shop ? 'print' : v.zone_code }
    const body = kind === 'shift_late' ? { ...base, start_time: v.start_time, hours: +v.hours, area_m2: v.area_m2 === '' || shop ? null : +v.area_m2, work_done: v.work_done,
      workshop: shop ? v.workshop : null, photo: shop ? null : pic } : { ...base, amount: +v.amount, category: v.category, paid_by: v.paid_by, note: v.note, receipt: pic }
    try { await api('/appeals', { method: 'POST', body }); done('Обращение ушло: сначала куратору, потом HEAD.') } catch (e) { setErr(e.message || String(e)) } finally { setBusy(false) }
  }
  return <div className="fixbox">
    <div className="segf"><button className={kind === 'shift_late' ? 'on' : ''} onClick={() => setKind('shift_late')}>Смену</button>
      <button className={kind === 'expense_late' ? 'on' : ''} onClick={() => setKind('expense_late')}>Расход</button></div>
    <label className="muted small">За какой день</label><input type="date" min={min} max={tday()} value={v.day} onChange={e => set({ ...v, day: e.target.value })} />
    {kind === 'shift_late' && d.workshop && <div className="segf"><button className={shop ? '' : 'on'} onClick={() => set({ ...v, workshop: '' })}>На объекте</button>
      <button className={shop ? 'on' : ''} onClick={() => set({ ...v, workshop: d.workshop[0] })}>Мастерская</button></div>}
    {shop ? <div className="chips">{d.workshop.map(t => <button key={t} className={v.workshop === t ? 'on' : ''} onClick={() => set({ ...v, workshop: t })}>{t}</button>)}</div> : <>
      <label className="muted small">Объект</label>
      <select value={v.object_id} onChange={e => set({ ...v, object_id: +e.target.value })}>
        {(kind === 'expense_late' ? d.objects : objs).map(o => <option key={o.id} value={o.id}>{o.id ? `№${o.id} · ` : ''}{o.title}{o.city ? ` — ${o.city}` : ''}</option>)}</select>
      {d.zones.length > 1 && <div className="segf">{d.zones.map(z => <button key={z} className={v.zone_code === z ? 'on' : ''} onClick={() => set({ ...v, zone_code: z })}>{ZONE[z]}</button>)}</div>}</>}
    {kind === 'shift_late' ? <>
      <div className="pair"><div><label className="muted small">Начали в</label><input type="time" value={v.start_time} onChange={e => set({ ...v, start_time: e.target.value })} /></div>
        <div><label className="muted small">Часов (до 48)</label><input inputMode="decimal" value={v.hours} onChange={e => set({ ...v, hours: num(e.target.value) })} /></div></div>
      {!shop && <><label className="muted small">Сделано, м²</label><input inputMode="decimal" value={v.area_m2} onChange={e => set({ ...v, area_m2: num(e.target.value) })} /></>}
      <label className="muted small">Что сделал</label><textarea rows={2} value={v.work_done} onChange={e => set({ ...v, work_done: e.target.value })} />
      {!shop && <label className="photo snap add"><span>{pic ? '✓ Фото выбрано' : '🖼 Фото работы (по возможности)'}</span>
        <input type="file" accept="image/*" hidden onChange={async e => { const f = e.target.files[0]; e.target.value = ''; f && setPic(await shrink(f)) }} /></label>}
    </> : <>
      <label className="muted small">Категория</label>
      <select value={v.category} onChange={e => set({ ...v, category: e.target.value })}>{d.categories.map(c => <option key={c.code} value={c.code}>{c.title}</option>)}</select>
      <label className="muted small">Сумма, ₸</label><input inputMode="decimal" value={v.amount} onChange={e => set({ ...v, amount: num(e.target.value) })} />
      <div className="segf"><button className={v.paid_by === 'own' ? 'on' : ''} onClick={() => set({ ...v, paid_by: 'own' })}>Свои деньги</button>
        <button className={v.paid_by === 'company' ? 'on' : ''} onClick={() => set({ ...v, paid_by: 'company' })}>Компании</button></div>
      <input placeholder="Комментарий" value={v.note} onChange={e => set({ ...v, note: e.target.value })} />
      <Receipt value={pic} pick={async f => setPic(await shrink(f))} />
    </>}
    <label className="muted small">Почему не внёс вовремя</label><textarea rows={2} value={why} onChange={e => setWhy(e.target.value)} placeholder="Например: не было связи на объекте" />
    {err && <p className="small why">{err}</p>}
    <div className="seg"><button className="mini" disabled={!ok || busy} onClick={send}>{busy ? 'Отправляю…' : 'Отправить'}</button><button className="ghost mini" onClick={close}>Отмена</button></div>
  </div>
}

export function Appeals({ reload }) {
  const [list, setList] = useState(null)
  const [d, setD] = useState(null)
  const [open, setOpen] = useState(false)
  const [msg, setMsg] = useState('')
  const load = () => api('/appeals/my').then(setList, () => setList([]))
  useEffect(() => { load() }, [reload])
  const start = () => { setMsg(''); d ? setOpen(true) : api('/work/dict').then(x => { setD(x); setOpen(true) }, e => setMsg(e.message)) }
  const cancel = id => api(`/appeals/${id}/cancel`, { method: 'POST' }).then(load)
  return <div className="card"><h2>Исправить или внести поздно</h2>
    <p className="small muted">Не внёс смену или расход вовремя, или ошибся? Подай обращение: сначала его смотрит куратор, утверждает HEAD.
      Ошибку в записи — кнопкой «Ошибка? Обращение» под ней в «Мои смены» и «Мои расходы».</p>
    {msg && <p className="small">{msg}</p>}
    {open && d ? <LateAppeal d={d} close={() => setOpen(false)} done={t => { setOpen(false); setMsg(t); load() }} />
      : <button className="ghost mini" onClick={start}>Не внёс вовремя</button>}
    {list?.map(a => <div key={a.id} className="row"><div><AppealView a={a} /><CurMark x={a} />{a.reason && <div className="small">HEAD: {a.reason}</div>}</div>
      <StatusMark status={a.status} />{a.status === 'submitted' && <a onClick={() => cancel(a.id)}>отменить</a>}</div>)}
  </div>
}

const STAGE = { rated: 'Оценил куратор', direct: 'Смены кураторов и без куратора', late: 'Без оценки: куратор не успел за 24 ч', wait: 'Ждут оценки куратора' }
export function Review() {
  const [r, setR] = useState(null)
  const [pays, setPays] = useState(null)   // оплаты клиентов, которые внесли МОП (HEAD 10.11) — только у HEAD
  const load = () => api('/review').then(setR, () => setR({ shifts: [], expenses: [], appeals: [] }))
  const loadPays = () => api('/fin/payments/check').then(setPays, () => setPays(null))
  useEffect(() => { load(); loadPays() }, [])
  if (!r) return <div className="card muted">Загрузка…</div>
  const cur = r.curator
  const apps = r.appeals || []
  const pay = (id, ok) => (ok || confirm('Отменить оплату? Она останется в журнале зачёркнутой, «Поступило» в сделке уменьшится.')) &&
    api(`/fin/ledger/${id}/${ok ? 'check' : 'cancel'}`, { method: 'POST' }).then(loadPays, e => alert(e.message))
  const decide = (path, approve) => {
    const reason = approve ? null : prompt('Причина отказа')
    if (!approve && !reason) return
    api(path, { method: 'POST', body: { approve, reason } }).then(load, e => alert(e.message))
  }
  const good = r.shifts.filter(x => x.cur_stars >= 4).length
  const bulk = () => confirm(`Утвердить ${good} смен с оценкой куратора 4–5★?`) &&
    api('/review/bulk', { method: 'POST', body: { min_stars: 4 } }).then(load, e => alert(e.message))
  const Item = ({ k, x, children }) => <div className="row">
    <div><b>{x.person_name}</b> · {x.object_title}{x.backfill && <span className="tag draft">задним числом</span>}<br /><span className="muted small">{children}</span>
      {x.work_done && <div className="small">Сделал: {x.work_done}</div>}
      {(x.photo_before_url || x.photo_after_url) && <div className="pair">{x.photo_before_url && <a href={x.photo_before_full} target="_blank" rel="noreferrer"><img src={x.photo_before_url} alt="до" /></a>}
        {x.photo_after_url && <a href={x.photo_after_full} target="_blank" rel="noreferrer"><img src={x.photo_after_url} alt="после" /></a>}</div>}
      <More x={x} />
      {cur ? null : <CurMark x={x} />}
      {k === 'shift' && <FixShift x={x} done={load} />}
      {cur && <RateBox path={`/${k}/${x.id}/rate`} stars={k === 'shift'} done={load} />}</div>
    {!cur && <div className="seg"><button onClick={() => decide(`/${k}/${x.id}/review`, true)}>✓</button><button className="ghost" onClick={() => decide(`/${k}/${x.id}/review`, false)}>✕</button></div>}
  </div>
  const Appeal = ({ a }) => <div className="row">
    <div><b>{a.person_name}</b><AppealView a={a} />
      {cur ? <RateBox path={`/appeals/${a.id}/rate`} stars={a.kind === 'shift_late'} done={load} /> : <CurMark x={a} />}
      {!cur && a.closed && <div className="small muted">Месяц закрыт — сумма пойдёт в ФОТ текущего месяца, прошлый не меняется.</div>}</div>
    {!cur && <div className="seg"><button onClick={() => decide(`/appeals/${a.id}/decide`, true)}>✓</button><button className="ghost" onClick={() => decide(`/appeals/${a.id}/decide`, false)}>✕</button></div>}
  </div>
  const shiftLine = x => <>{when(x.started_at, x.ended_at)}{x.area_m2 ? ` · ${+x.area_m2} м²` : ''} · {ZONE[x.zone_code]}{x.plan_m2 ? ` · ${x.zone_code === 'print' ? 'план' : 'норма'} ${m2(x.plan_m2)} м²` : ''}{x.kpd != null ? ` · КПД ${pct(x.kpd)}` : ''}{x.printer ? ` · ${x.printer}` : ''}</>
  const expLine = x => <>{money(x.amount)}{x.category_title && !(x.object_title || '').includes(x.category_title) ? ' · ' + x.category_title : ''} · {x.paid_by === 'own' ? 'свои' : 'компании'}{x.note ? ' · ' + x.note : ''}{x.receipt_url ? <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></> : ' · без чека'}</>
  // HEAD: по этапам; «ждут куратора» — свёрнуто внизу, но утвердить можно и сразу
  const groups = (list, k, line) => {
    const by = st => list.filter(x => x.stage === st).sort((a, b) => (b.cur_stars || 0) - (a.cur_stars || 0))
    return <>{['rated', 'direct', 'late'].map(st => by(st).length ? <div key={st}><h3 className="small muted stagehd">{STAGE[st]} · {by(st).length}</h3>
      {by(st).map(x => <Item key={x.id} k={k} x={x}>{line(x)}</Item>)}</div> : null)}
      {by('wait').length ? <details className="how"><summary className="small muted">{STAGE.wait} · {by('wait').length}</summary>
        {by('wait').map(x => <Item key={x.id} k={k} x={x}>{line(x)}</Item>)}</details> : null}</>
  }
  if (cur) return <>
    <div className="card"><p className="small muted">Ты ставишь оценку и комментарий, утверждает HEAD. Не оценишь за 24 ч — запись уйдёт к HEAD без оценки.
      Смены кураторов идут сразу к HEAD.</p></div>
    <div className="card"><h2>Оценить смены</h2>
      {r.shifts.length ? r.shifts.map(x => <Item key={x.id} k="shift" x={x}>{shiftLine(x)}</Item>) : <p className="muted">Всё оценено</p>}</div>
    {apps.length > 0 && <div className="card"><h2>Обращения</h2>{apps.map(a => <Appeal key={a.id} a={a} />)}</div>}
    <div className="card"><h2>Проверить расходы</h2>
      {r.expenses.length ? r.expenses.map(x => <Item key={x.id} k="expense" x={x}>{expLine(x)}</Item>) : <p className="muted">Всё проверено</p>}</div>
  </>
  return <>
    <div className="card"><h2>Смены на утверждение</h2>
      {good > 0 && <button className="mini" onClick={bulk}>Утвердить все с оценкой 4–5★ · {good}</button>}
      {r.shifts.length ? groups(r.shifts, 'shift', shiftLine) : <p className="muted">Всё проверено</p>}
    </div>
    {apps.length > 0 && <div className="card"><h2>Обращения на правку</h2>{apps.map(a => <Appeal key={a.id} a={a} />)}</div>}
    {pays && <div className="card"><h2>Оплаты клиентов на сверку</h2>
      {pays.length ? pays.map(x => <div key={x.id} className="row">
        <div><b>{money(x.amount)}</b> · сделка № {x.deal_id}<br /><span className="muted small">{[new Date(x.op_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }),
          x.account_title, (x.note || '').replace(`${x.deal_id} · `, '')].filter(Boolean).join(' · ')}{x.receipt_url ? <> · <a href={x.receipt_url} target="_blank" rel="noreferrer">чек</a></> : ' · без чека'}</span></div>
        <div className="seg"><button onClick={() => pay(x.id, true)}>✓</button><button className="ghost" onClick={() => pay(x.id, false)}>✕</button></div>
      </div>) : <p className="muted">Всё сверено</p>}
      <p className="small muted">✓ — деньги пришли, сумма и чек совпадают с выпиской. ✕ — ошибка: оплата отменяется, итог сделки в Битриксе пересчитается.</p>
    </div>}
    <div className="card"><h2>Расходы на утверждение</h2>
      {r.expenses.length ? groups(r.expenses, 'expense', expLine) : <p className="muted">Всё проверено</p>}
    </div>
  </>
}

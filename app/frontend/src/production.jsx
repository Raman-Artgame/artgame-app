import React, { useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import { Viewer, download, uploadBig } from './objects.jsx'
import { Sheet } from './ui.jsx'

// «Продакшн» (HEAD 08.11): Главный художник, Художник-Про, Мастер настенной печати грузят полноценный материал с объекта —
// фото, видео, готовые рилс. Всё уходит в «МЕДИА / Отчёты» папки сделки; HEAD утверждает лучшее → копия в «МЕДИА / Продакшн / Фото» или «/ Видео» (рилс остаётся в «МЕДИА / Рилс»).
// Рилс после утверждения — плюсом к оплате (ставка и лимит в месяц — из «Значений»).
// HEAD 24.11: «очень не удобно и коряво, видео не загружаются… блок нужно полноценно доработать» — загрузка очередью с полосками
// и повтором (файл идёт частями, обрыв связи не рвёт загрузку), фото и видео одной кнопкой; у HEAD — плитки по проектам,
// просмотр с листанием и кнопками прямо в нём, «Утвердить все», возврат с готовыми причинами.
const TYPES = [['photo', 'Фото'], ['video', 'Видео'], ['reels', 'Рилс']]
const TNAME = Object.fromEntries(TYPES)
const RV = { pending: ['у HEAD', 'warn'], approved: ['в Продакшн', 'ok'], rejected: ['вернул', 'hot'] }
const money = n => Number(n || 0).toLocaleString('ru-RU') + ' ₸'
const fsize = b => b >= 1e9 ? (b / 1e9).toFixed(2).replace('.', ',') + ' ГБ' : b >= 1e6 ? (b / 1e6).toFixed(1).replace('.', ',') + ' МБ' : Math.ceil(b / 1e3) + ' КБ'
const first = n => (n || '').split(' ').slice(-1)[0]
const WHY = ['Тёмное', 'Смазано', 'Дубль', 'Не тот ракурс', 'Мусор в кадре', 'Не готовый объект']

export function Production({ me }) {
  const head = me.role_code === 'head'
  const lib = head || me.role_code === 'lead_designer'   // медиатека для монтажа рилс (HEAD 10.11)
  const [view, setView] = useState(head ? 'review' : lib ? 'lib' : 'add')
  return <>
    <div className="card dark prodhead"><span className="kick">Продакшн</span>
      <h2>Материал с объекта</h2>
      <p className="small muted">{head ? '«На утверждение» — материал по проектам. Нажми на плитку: откроется крупно, листается, «Утверждаю» и «Вернуть» прямо там. Утверждённое фото уходит в «МЕДИА / Продакшн / Фото», видео — в «Продакшн / Видео», рилс остаётся в «МЕДИА / Рилс» и идёт в оплату.'
        : 'Фото и видео готового объекта — сюда. Без них проект не сдать и сделку не закрыть. HEAD смотрит и лучшее утверждает; статус — в «Моё».'}</p>
    </div>
    <div className="segf">
      {head && <button className={view === 'review' ? 'on' : ''} onClick={() => setView('review')}>На утверждение</button>}
      {lib && <button className={view === 'lib' ? 'on' : ''} onClick={() => setView('lib')}>Медиа</button>}
      <button className={view === 'add' || view === 'reels' ? 'on' : ''} onClick={() => setView('add')}>Загрузить</button>
      <button className={view === 'mine' ? 'on' : ''} onClick={() => setView('mine')}>Моё</button>
    </div>
    {view === 'review' ? <Review /> : view === 'lib' ? <Library onReels={() => setView('reels')} /> : view === 'add' || view === 'reels' ? <Add key={view} initial={view === 'reels' ? 'reels' : 'media'} onDone={() => setView('mine')} /> : <Mine />}
  </>
}

// Плитка-превью: фото — миниатюрой, видео — кадром с Диска (если он уже готов), иначе значок
function Pv({ x }) {
  const [bad, setBad] = useState(false)
  const src = x.thumb || x.poster
  const video = x.media_type !== 'photo'
  return <>{src && !bad ? <img src={src} alt={x.name} loading="lazy" onError={() => setBad(true)} /> : <span className="pvic">{video ? '▶' : '🖼'}</span>}
    {video && <i className="pvtag">{x.media_type === 'reels' ? '🎬 рилс' : '▶ видео'}</i>}</>
}

let seq = 0
function Add({ onDone, initial }) {
  const [objs, setObjs] = useState(null)
  const [obj, setObj] = useState(null)
  const [mode, setMode] = useState(initial || 'media')   // media — фото и видео с объекта; reels — готовый рилс
  const [rate, setRate] = useState(null)
  const [q, setQ] = useState([])
  const qr = useRef([]), running = useRef(false), alive = useRef(true)
  useEffect(() => {
    api('/objects').then(l => { setObjs(l); setObj(l[0]?.id || null) }, () => setObjs([]))
    api('/media?scope=mine').then(r => setRate(r.reels), () => {})
    return () => { alive.current = false }
  }, [])
  const upd = (id, patch) => { qr.current = qr.current.map(x => x.id === id ? { ...x, ...patch } : x); alive.current && setQ(qr.current) }
  const run = async () => {
    if (running.current) return
    running.current = true
    for (;;) {
      const it = qr.current.find(x => x.st === 'wait')
      if (!it) break
      upd(it.id, { st: 'run', pct: 0 })
      let shown = 0
      try {
        await uploadBig(it.obj, 'media', it.file, p => { if (p - shown >= 0.01 || p === 1) { shown = p; upd(it.id, { pct: p }) } }, { media_type: it.type })
        upd(it.id, { st: 'ok', pct: 1 })
      } catch (e) { upd(it.id, { st: 'err', err: e.message || 'не загрузилось' }) }
    }
    running.current = false
    if (alive.current && qr.current.length && qr.current.every(x => x.st === 'ok')) onDone()
  }
  const pick = files => {
    const add = [...files].map(f => {
      const img = (f.type || '').startsWith('image/'), vid = (f.type || '').startsWith('video/') || /\.(mp4|mov|m4v|avi|mkv|webm)$/i.test(f.name)
      const type = mode === 'reels' ? 'reels' : img ? 'photo' : 'video'
      const bad = mode === 'reels' ? !vid : !img && !vid
      return { id: ++seq, file: f, obj, type, st: bad ? 'err' : 'wait', pct: 0, err: bad ? (mode === 'reels' ? 'рилс — это видео' : 'не фото и не видео') : '', fatal: bad }
    })
    qr.current = [...qr.current, ...add]; setQ(qr.current); run()
  }
  if (!objs) return <div className="card muted">Загрузка…</div>
  if (!objs.length) return <div className="card muted">Активных объектов нет.</div>
  const busy = q.some(x => x.st === 'run' || x.st === 'wait')
  const ok = q.filter(x => x.st === 'ok').length, bad = q.filter(x => x.st === 'err').length
  return <div className="card prodadd">
    <label className="muted">Объект</label>
    <div className="objpick">{objs.map(o => <button key={o.id} className={o.id === obj ? 'on' : ''} disabled={busy} onClick={() => setObj(o.id)}>
      <b>№{o.id}</b> {o.title}{o.city ? <span> · {o.city}</span> : null}</button>)}</div>
    <label className="muted">Что загружаешь</label>
    <div className="seg"><button className={mode === 'media' ? '' : 'ghost'} disabled={busy} onClick={() => setMode('media')}>Фото и видео</button>
      <button className={mode === 'reels' ? '' : 'ghost'} disabled={busy} onClick={() => setMode('reels')}>Рилс</button></div>
    {mode === 'reels' ? (rate?.rate ? <p className="small">Готовый рилс: <b>+{money(rate.rate)}</b> после утверждения HEAD{rate.max ? `, до ${rate.max} в месяц` : ''}.</p>
      : <p className="small muted">Готовый смонтированный рилс. HEAD утверждает.</p>)
      : <p className="small muted">Можно выбрать сразу много: фото готового объекта, процесс, таймлапс, до и после. Приложение само разложит фото и видео.</p>}
    <label className="photo big"><span>{mode === 'reels' ? '🎬 Выбрать рилс' : '📷 Выбрать фото и видео'}</span>
      <input type="file" accept={mode === 'reels' ? 'video/*' : 'image/*,video/*'} multiple hidden onChange={e => { const f = e.target.files; f.length && pick(f); e.target.value = '' }} /></label>
    {q.length > 0 && <div className="upq">
      <div className="head"><b>{busy ? `Загружаю: ${ok} из ${q.length}` : bad ? `Загружено ${ok} из ${q.length}` : `✓ Загружено: ${ok}`}</b>
        {!busy && ok > 0 && <button className="mini" onClick={onDone}>Смотреть «Моё»</button>}</div>
      {busy && <p className="small why">Не закрывай приложение и не блокируй экран, пока идёт загрузка. Пропала связь — продолжится сама с того же места.</p>}
      {q.map(x => <div key={x.id} className={'upi ' + x.st}>
        <div className="upn"><b>{x.file.name}</b><span className="small muted">{x.fatal ? '' : TNAME[x.type] + ' · '}{fsize(x.file.size)}</span></div>
        <span className="ups">{x.st === 'ok' ? '✓' : x.st === 'run' ? Math.round(x.pct * 100) + '%' : x.st === 'wait' ? 'ждёт' : '✕'}</span>
        {(x.st === 'run' || x.st === 'ok') && <div className="bar"><i style={{ width: Math.round(x.pct * 100) + '%' }} /></div>}
        {x.st === 'err' && <div className="uperr"><span className="small why">Не загрузилось: {x.err}</span>
          {!x.fatal && <button className="mini" onClick={() => { upd(x.id, { st: 'wait', err: '' }); run() }}>Повторить</button>}
          <button className="ghost mini" onClick={() => { qr.current = qr.current.filter(i => i.id !== x.id); setQ(qr.current) }}>Убрать</button></div>}
      </div>)}
    </div>}
  </div>
}

function Item({ x, children, onOpen }) {
  return <div className="mitem">
    <button className="mthumb" onClick={() => onOpen(x)}><Pv x={x} /></button>
    <div className="mbody"><a onClick={() => onOpen(x)}><b>{x.name}</b></a>
      <div className="small muted">{TNAME[x.media_type]} · №{x.object_id} {x.object_title} · {x.by}</div>
      {children}</div>
  </div>
}

// Медиатека (HEAD 10.11): Главный дизайнер видит видео и фото со всех объектов, скачивает, монтирует рилс
// и загружает готовый рилс («Загрузить → Рилс») — он уходит HEAD на утверждение.
function Library({ onReels }) {
  const [type, setType] = useState('video')
  const [d, setD] = useState(null)
  const [obj, setObj] = useState('')
  const [open, setOpen] = useState(null)
  useEffect(() => { setD(null); api(`/media?scope=library&type=${type}`).then(setD, e => setD({ items: [], err: e.message })) }, [type])
  const objs = d ? [...new Map(d.items.map(x => [x.object_id, `№${x.object_id} ${x.object_title}`])).entries()] : []
  const items = d ? d.items.filter(x => !obj || x.object_id === +obj) : []
  return <div className="card">
    <p className="small muted">Материал с объектов от команды. Скачай, смонтируй рилс и загрузи его: «Загрузить → Рилс» — он уйдёт HEAD на утверждение.</p>
    <div className="seg">{TYPES.map(([k, t]) => <button key={k} className={type === k ? '' : 'ghost'} onClick={() => { setType(k); setObj('') }}>{t}</button>)}</div>
    {objs.length > 1 && <select value={obj} onChange={e => setObj(e.target.value)}><option value="">Все объекты</option>
      {objs.map(([id, t]) => <option key={id} value={id}>{t}</option>)}</select>}
    {!d ? <p className="muted">Загрузка…</p> : d.err ? <p className="small why">{d.err}</p> : !items.length ? <p className="muted small">Пока пусто.</p> :
      items.map(x => <div key={x.id} className="mitem">
        <button className="mthumb" onClick={() => setOpen(x)}><Pv x={x} /></button>
        <div className="mbody"><a onClick={() => setOpen(x)}><b>{x.name}</b></a>
          <div className="small muted">№{x.object_id} {x.object_title} · {x.by} · {new Date(x.created_at).toLocaleDateString('ru-RU')}{x.review === 'approved' ? ' · в Продакшн' : ''}</div></div>
        <button className="ghost mini" aria-label="Скачать" onClick={() => download(x)}>⬇</button>
      </div>)}
    <button className="ghost" onClick={onReels}>🎬 Загрузить готовый рилс</button>
    <Viewer f={open} onClose={() => setOpen(null)} list={items.length > 1 ? items : null} onNav={setOpen} />
  </div>
}

function Mine() {
  const [d, setD] = useState(null)
  const [f, setF] = useState('')
  const [open, setOpen] = useState(null)
  const load = () => api('/media?scope=mine').then(setD, () => setD({ items: [] }))
  useEffect(() => { load() }, [])
  if (!d) return <div className="card muted">Загрузка…</div>
  const n = s => d.items.filter(x => x.review === s).length
  const items = d.items.filter(x => !f || x.review === f)
  return <div className="card">
    <div className="mstats">{[['pending', 'у HEAD'], ['approved', 'в Продакшн'], ['rejected', 'вернул']].map(([k, t]) =>
      <div key={k} role="button" className={f === k ? 'on' : ''} onClick={() => setF(f === k ? '' : k)}><b>{n(k)}</b><span>{t}</span></div>)}</div>
    {!d.items.length && <p className="muted small">Пока ничего не загружено. «Загрузить» — фото и видео готового объекта.</p>}
    {d.items.length > 0 && !items.length && <p className="muted small">Здесь пусто.</p>}
    {items.map(x => <Item key={x.id} x={x} onOpen={setOpen}><span className={'badge ' + RV[x.review][1]} style={{ marginLeft: 0 }}>{RV[x.review][0]}</span>
      {x.review_note && <div className="small why">HEAD: {x.review_note}</div>}
      {x.review === 'rejected' && <div><a className="small" onClick={() => api(`/files/${x.id}/archive`, { method: 'POST' }).then(load, () => {})}>Убрать из списка</a></div>}</Item>)}
    <Viewer f={open} onClose={() => setOpen(null)} list={items.length > 1 ? items : null} onNav={setOpen} />
  </div>
}

function Review() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState('')
  const [obj, setObj] = useState(0)
  const [open, setOpen] = useState(null)
  const [back, setBack] = useState(null)   // что возвращаем: {x, note}
  const [busy, setBusy] = useState('')
  const [sure, setSure] = useState(0)      // «Утвердить все» — вторым нажатием
  const load = () => api('/media?scope=review').then(setD, e => setMsg(e.message))
  useEffect(() => { load() }, [])
  if (!d) return <div className="card muted">{msg || 'Загрузка…'}</div>
  const groups = [...d.items.reduce((m, x) => m.set(x.object_id, [...(m.get(x.object_id) || []), x]), new Map()).entries()]
  const shown = groups.filter(([id]) => !obj || id === obj)
  const flat = shown.flatMap(([, l]) => l)
  const drop = x => setD(v => ({ ...v, items: v.items.filter(i => i.id !== x.id) }))
  const send = (x, approve, note) => api(`/media/${x.id}/review`, { method: 'POST', body: { approve, note: note || null } }).then(() => drop(x))
  const decide = async (x, approve, note) => {
    setMsg(''); setBusy(approve ? 'Утверждаю…' : 'Возвращаю…')
    const i = flat.findIndex(y => y.id === x.id), next = flat[i + 1] || flat[i - 1] || null
    try { await send(x, approve, note); if (open && open.id === x.id) setOpen(next); setBack(null) } catch (e) { setMsg(`${x.name}: ${e.message}`) }
    setBusy('')
  }
  const all = async list => {
    setSure(0); setMsg('')
    for (const [i, x] of list.entries()) {
      setBusy(`Утверждаю ${i + 1} из ${list.length}…`)
      try { await send(x, true) } catch (e) { setMsg(`Остановился на «${x.name}»: ${e.message}`); break }
    }
    setBusy('')
  }
  const btns = x => <div className="seg rvbtns"><button disabled={!!busy} onClick={() => decide(x, true)}>✓ Утверждаю</button>
    <button className="ghost" disabled={!!busy} aria-label="Вернуть" onClick={() => setBack({ x, note: '' })}>↩ Вернуть</button></div>
  return <>
    {(msg || busy) && <div className="card"><p className={'small ' + (msg ? 'why' : 'muted')} style={{ margin: 0 }}>{msg || busy}</p></div>}
    {!d.items.length && <div className="card"><p className="muted" style={{ margin: 0 }}>Всё утверждено.</p>
      <p className="small muted">Новый материал появится здесь и цифрой в «Пульте».</p></div>}
    {groups.length > 1 && <div className="chips rvobj"><button className={obj ? '' : 'on'} onClick={() => setObj(0)}>Все<span>{d.items.length}</span></button>
      {groups.map(([id, l]) => <button key={id} className={obj === id ? 'on' : ''} onClick={() => setObj(id)}>№{id}<span>{l.length}</span></button>)}</div>}
    {shown.map(([id, l]) => {
      const cnt = TYPES.map(([k, t]) => [t.toLowerCase(), l.filter(x => x.media_type === k).length]).filter(c => c[1]).map(c => c.join(' ')).join(' · ')
      return <div key={id} className="card rvgroup">
        <div className="head"><h3>№{id} {l[0].object_title}</h3></div>
        <p className="small muted">{l[0].object_city ? l[0].object_city + ' · ' : ''}{cnt} · от: {[...new Set(l.map(x => first(x.by)))].join(', ')}</p>
        <div className="rvgrid">{l.map(x => <div key={x.id} className="rvtile">
          <button className="rvpv" onClick={() => setOpen(x)} aria-label={'Открыть ' + x.name}><Pv x={x} /></button>
          <div className="small rvname">{x.name}</div>
          {btns(x)}
        </div>)}</div>
        {l.length > 1 && <button className={sure === id ? '' : 'ghost'} disabled={!!busy} onClick={() => sure === id ? all(l) : setSure(id)}>
          {sure === id ? `Точно утвердить все ${l.length}?` : `✓ Утвердить все ${l.length} по проекту`}</button>}
        {l.some(x => x.media_type === 'reels') && <p className="small muted">Рилс после утверждения — плюсом к оплате автора.</p>}
      </div>
    })}
    <Viewer f={open} onClose={() => setOpen(null)} list={flat.length > 1 ? flat : null} onNav={setOpen}
      extra={open && <><p className="small" style={{ margin: '0 0 6px' }}>№{open.object_id} {open.object_title} · {TNAME[open.media_type]} · {open.by}</p>{btns(open)}</>} />
    {back && <Sheet title="Вернуть автору" onClose={() => setBack(null)}>
      <p className="small muted">{back.x.name} · {back.x.by}. Причину увидит автор в «Моё».</p>
      <div className="chips">{WHY.map(w => <button key={w} className={back.note === w ? 'on' : ''} onClick={() => setBack({ ...back, note: w })}>{w}</button>)}</div>
      <input placeholder="Что не так" value={back.note} onChange={e => setBack({ ...back, note: e.target.value })} />
      <button disabled={!!busy || back.note.trim().length < 2} onClick={() => decide(back.x, false, back.note.trim())}>↩ Вернуть</button>
    </Sheet>}
  </>
}

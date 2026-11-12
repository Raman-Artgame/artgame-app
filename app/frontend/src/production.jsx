import React, { useEffect, useState } from 'react'
import { api } from './api.js'
import { Viewer, download, uploadBig } from './objects.jsx'

// «Продакшн» (HEAD 08.11): Главный художник, Художник-Про, Мастер настенной печати грузят полноценный материал с объекта —
// фото, видео, готовые рилс. Всё уходит в «МЕДИА / Отчёты» папки сделки; HEAD утверждает лучшее → копия в «МЕДИА / Продакшн / Фото» или «/ Видео» (рилс остаётся в «МЕДИА / Рилс»).
// Рилс после утверждения — плюсом к оплате (ставка и лимит в месяц — из «Значений»).
const TYPES = [['photo', 'Фото'], ['video', 'Видео'], ['reels', 'Рилс']]
const RV = { pending: ['у HEAD', 'warn'], approved: ['в Продакшн', 'ok'], rejected: ['вернул', 'hot'] }
const money = n => Number(n || 0).toLocaleString('ru-RU') + ' ₸'
const ACCEPT = { photo: 'image/*', video: 'video/*', reels: 'video/*' }

export function Production({ me }) {
  const head = me.role_code === 'head'
  const lib = head || me.role_code === 'lead_designer'   // медиатека для монтажа рилс (HEAD 10.11)
  const [view, setView] = useState(head ? 'review' : lib ? 'lib' : 'add')
  return <>
    <div className="card dark prodhead"><span className="kick">Продакшн</span>
      <h2>Материал с объекта</h2>
      <p className="small muted">{head ? 'Ниже «На утверждение»: под каждым материалом «Утверждаю» — фото уходит в «МЕДИА / Продакшн / Фото», видео — в «Продакшн / Видео», рилс остаётся в «МЕДИА / Рилс» и идёт в оплату, «Вернуть» — с причиной. Сколько ждёт — видно в «Пульте».'
        : 'Фото и видео ложатся в папку сделки «МЕДИА / Отчёты», рилс — в «МЕДИА / Рилс». HEAD смотрит у себя в «Продакшн → На утверждение»: лучшее утверждает — фото уходит в «МЕДИА / Продакшн / Фото», видео — в «Продакшн / Видео», статус виден в «Моё».'}</p>
    </div>
    <div className="segf">
      {head && <button className={view === 'review' ? 'on' : ''} onClick={() => setView('review')}>На утверждение</button>}
      {lib && <button className={view === 'lib' ? 'on' : ''} onClick={() => setView('lib')}>Медиа</button>}
      <button className={view === 'add' || view === 'reels' ? 'on' : ''} onClick={() => setView('add')}>Загрузить</button>
      <button className={view === 'mine' ? 'on' : ''} onClick={() => setView('mine')}>Моё</button>
    </div>
    {view === 'review' ? <Review /> : view === 'lib' ? <Library onReels={() => setView('reels')} /> : view === 'add' || view === 'reels' ? <Add key={view} initial={view === 'reels' ? 'reels' : 'photo'} onDone={() => setView('mine')} /> : <Mine />}
  </>
}

function Add({ onDone, initial }) {
  const [objs, setObjs] = useState(null)
  const [obj, setObj] = useState(null)
  const [type, setType] = useState(initial || 'photo')
  const [busy, setBusy] = useState('')
  const [rate, setRate] = useState(null)
  useEffect(() => {
    api('/objects').then(l => { setObjs(l); setObj(l[0]?.id || null) }, () => setObjs([]))
    api('/media?scope=mine').then(r => setRate(r.reels), () => {})
  }, [])
  if (!objs) return <div className="card muted">Загрузка…</div>
  if (!objs.length) return <div className="card muted">Активных объектов нет.</div>
  const send = async files => {
    const all = [...files]
    for (const [i, f] of all.entries()) {
      try {
        await uploadBig(obj, 'media', f, p => setBusy(`${i + 1} из ${all.length} · ${f.name}: ${Math.round(p * 100)}%`), { media_type: type })
      } catch (e) { setBusy(`Не загрузилось «${f.name}»: ${e.message}. Нужна сеть — попробуй ещё раз.`); return }
    }
    setBusy(''); onDone()
  }
  return <div className="card">
    <label className="muted">Объект</label>
    <div className="objpick">{objs.map(o => <button key={o.id} className={o.id === obj ? 'on' : ''} onClick={() => setObj(o.id)}>
      <b>№{o.id}</b> {o.title}{o.city ? <span> · {o.city}</span> : null}</button>)}</div>
    <label className="muted">Что загружаешь</label>
    <div className="seg">{TYPES.map(([k, t]) => <button key={k} className={type === k ? '' : 'ghost'} onClick={() => setType(k)}>{t}</button>)}</div>
    {type === 'reels' && rate?.rate ? <p className="small">Готовый рилс: <b>+{money(rate.rate)}</b> после утверждения HEAD{rate.max ? `, до ${rate.max} в месяц` : ''}.</p> : null}
    {type === 'video' && <p className="small muted">Исходники: процесс, таймлапс, до/после — для монтажа.</p>}
    <label className={'photo big' + (busy ? ' busy' : '')}><span>{type === 'photo' ? '📷 Выбрать фото' : '🎬 Выбрать видео'}</span>
      <input type="file" accept={ACCEPT[type]} multiple hidden disabled={!!busy} onChange={e => e.target.files.length && send(e.target.files)} /></label>
    {busy && <p className="small muted">{busy}</p>}
  </div>
}

function Item({ x, children }) {
  return <div className="mitem">
    <a className="mthumb" href={x.url} target="_blank" rel="noreferrer">{x.thumb ? <img src={x.thumb} alt={x.name} loading="lazy" /> : <span>{x.media_type === 'photo' ? '🖼' : '▶'}</span>}</a>
    <div className="mbody"><b>{x.name}</b>
      <div className="small muted">{TYPES.find(t => t[0] === x.media_type)?.[1]} · №{x.object_id} {x.object_title} · {x.by}</div>
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
        <button className="mthumb" onClick={() => setOpen(x)}>{x.thumb ? <img src={x.thumb} alt="" loading="lazy" /> : <span>▶</span>}</button>
        <div className="mbody"><a onClick={() => setOpen(x)}><b>{x.name}</b></a>
          <div className="small muted">№{x.object_id} {x.object_title} · {x.by} · {new Date(x.created_at).toLocaleDateString('ru-RU')}{x.review === 'approved' ? ' · в Продакшн' : ''}</div></div>
        <button className="ghost mini" aria-label="Скачать" onClick={() => download(x)}>⬇</button>
      </div>)}
    <button className="ghost" onClick={onReels}>🎬 Загрузить готовый рилс</button>
    <Viewer f={open} onClose={() => setOpen(null)} />
  </div>
}

function Mine() {
  const [d, setD] = useState(null)
  useEffect(() => { api('/media?scope=mine').then(setD, () => setD({ items: [] })) }, [])
  if (!d) return <div className="card muted">Загрузка…</div>
  const n = s => d.items.filter(x => x.review === s).length
  return <div className="card">
    <div className="mstats"><div><b>{n('pending')}</b><span>у HEAD</span></div><div><b>{n('approved')}</b><span>в Продакшн</span></div><div><b>{n('rejected')}</b><span>вернул</span></div></div>
    {!d.items.length && <p className="muted small">Пока ничего не загружено.</p>}
    {d.items.map(x => <Item key={x.id} x={x}><span className={'badge ' + RV[x.review][1]} style={{ marginLeft: 0 }}>{RV[x.review][0]}</span>
      {x.review_note && <div className="small why">HEAD: {x.review_note}</div>}</Item>)}
  </div>
}

function Review() {
  const [d, setD] = useState(null)
  const [msg, setMsg] = useState('')
  const load = () => api('/media?scope=review').then(setD, e => setMsg(e.message))
  useEffect(() => { load() }, [])
  if (!d) return <div className="card muted">{msg || 'Загрузка…'}</div>
  const decide = (x, approve) => {
    const note = approve ? null : prompt('Что не так? (увидит автор)')
    if (!approve && !note) return
    api(`/media/${x.id}/review`, { method: 'POST', body: { approve, note } }).then(load, e => setMsg(e.message))
  }
  return <div className="card">
    {msg && <p className="small why">{msg}</p>}
    {!d.items.length && <p className="muted">Всё утверждено.</p>}
    {d.items.map(x => <Item key={x.id} x={x}>
      <div className="seg"><button onClick={() => decide(x, true)}>Утверждаю</button><button className="ghost" onClick={() => decide(x, false)}>Вернуть</button></div>
      {x.media_type === 'reels' && <div className="small muted">Рилс после утверждения — плюсом к оплате автора.</div>}
    </Item>)}
  </div>
}
